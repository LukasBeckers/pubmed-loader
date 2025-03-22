import json
import datetime
from typing import Dict, List, Any, Optional, Union
import requests
import pickle as pk
import xml.etree.ElementTree as ET
import time
import os
import threading
import zipfile
import uuid


def read_json(file_path: str) -> List[Dict[str, str]]:
    with open(file_path, "r", encoding="UTF-8") as file:
        data = json.load(file)
    return data


def json_to_txt(datapoint: Dict[str, str], save_path: str):
    with open(save_path, "w", encoding="UTF-8") as file:
        for key, value in datapoint.items():
            file.write(f"{key}: {value} \n\n")


# Base URL for all queries
BASE_URL = "https://eutils.ncbi.nlm.nih.gov"


class CustomPubMed:
    """Custom PubMed API Wrapper to handle large result sets beyond 9999 articles by splitting queries."""

    def __init__(
        self: object, tool: str = "PubMedSearcher", email: str = "my_email@example.com"
    ) -> None:
        """Initialize the CustomPubMed object."""
        self.tool = tool
        self.email = email
        self.parameters = {"tool": tool, "email": email, "db": "pubmed"}
        self._rateLimit = 3  # Max 3 requests per second
        self._requestsMade = []

    def _exceededRateLimit(self) -> bool:
        """Check if the rate limit has been exceeded."""
        current_time = datetime.datetime.now()
        # Keep only requests within the last second
        self._requestsMade = [
            req_time
            for req_time in self._requestsMade
            if req_time > current_time - datetime.timedelta(seconds=1)
        ]
        return len(self._requestsMade) >= self._rateLimit

    def _get(
        self: object, url: str, parameters: dict, output: str = "json"
    ) -> Union[Dict, str]:
        """Generic helper method to make a request to PubMed."""
        while self._exceededRateLimit():
            time.sleep(0.1)  # Wait before retrying
        response = requests.get(f"{BASE_URL}{url}", params=parameters)
        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            print(f"HTTP Error: {e}")
            print(f"URL: {response.url}")
            print(f"Response Text: {response.text}")
            raise
        self._requestsMade.append(datetime.datetime.now())
        if output == "json":
            return response.json()
        else:
            return response.text

    def search_with_history(self: object, query: str) -> Dict[str, Any]:
        """
        Perform an ESearch with history to handle large result sets.

        Returns:
            A dictionary containing 'count', 'WebEnv', and 'QueryKey'.
        """
        parameters = self.parameters.copy()
        parameters.update(
            {
                "term": query,
                "usehistory": "y",
                "retmax": 0,  # We don't need actual IDs here
            }
        )
        response = self._get("/entrez/eutils/esearch.fcgi", parameters, output="xml")
        root = ET.fromstring(response)
        count = int(root.findtext(".//Count"))
        webenv = root.findtext(".//WebEnv")
        query_key = root.findtext(".//QueryKey")
        return {"count": count, "WebEnv": webenv, "QueryKey": query_key}

    def fetch_articles(
        self: object,
        webenv: str,
        query_key: str,
        batch_size: int = 1000,
        max_results: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Fetch articles in batches using EFetch.

        Parameters:
            - webenv: The WebEnv string from ESearch.
            - query_key: The QueryKey from ESearch.
            - batch_size: Number of articles to fetch per request.
            - max_results: Maximum number of articles to fetch.

        Returns:
            A list of article dictionaries.
        """
        articles = []
        fetched = 0
        while True:
            if max_results and fetched >= max_results:
                break
            current_batch_size = batch_size
            if max_results:
                remaining = max_results - fetched
                if remaining < batch_size:
                    current_batch_size = remaining
            parameters = self.parameters.copy()
            parameters.update(
                {
                    "WebEnv": webenv,
                    "query_key": query_key,
                    "retstart": fetched,
                    "retmax": current_batch_size,
                    "rettype": "xml",
                    "retmode": "xml",
                }
            )
            response = self._get("/entrez/eutils/efetch.fcgi", parameters, output="xml")
            
            root = ET.fromstring(response)
            batch_articles = []
            for article in root.findall(".//PubmedArticle"):
                article_dict = self.parse_pubmed_article(article)
                batch_articles.append(article_dict)
            for book in root.findall(".//PubmedBookArticle"):
                book_dict = self.parse_pubmed_book_article(book)
                batch_articles.append(book_dict)
            if not batch_articles:
                break
            articles.extend(batch_articles)
            fetched += current_batch_size
            print(f"Fetched {fetched} articles...")
            # To comply with NCBI rate limits
            time.sleep(0.34)  # Approximately 3 requests per second
        return articles

    def parse_pubmed_article(self, article_element: ET.Element) -> Dict[str, Any]:
        """Parse a PubmedArticle XML element into a dictionary with comprehensive fields."""
        article_dict = {}

        # Extract PMID
        article_dict["PMID"] = article_element.findtext(".//PMID")

        # Extract Title
        title_element = article_element.find(".//ArticleTitle")
        if title_element is not None:
            article_dict["Title"] = ''.join(title_element.itertext()).strip()
        else:
            article_dict["Title"] = "No Title Available"

        # Extract Abstract
        abstract_text = ""
        abstract = article_element.find(".//Abstract")
        current_abstracts = []
        if abstract is not None:
            for abstract_section in abstract.findall("AbstractText"):
                # Use itertext to get all text within the AbstractText element, including nested tags
                section_text = ''.join(abstract_section.itertext()).strip()
                if section_text in current_abstracts:
                    print("Duplicate abstract section found, skipping.")
                    continue
                current_abstracts.append(section_text)
                
                label = abstract_section.get("Label")
                if label:
                    abstract_text += f"{label}: {section_text}\n"
                else:
                    abstract_text += f"{section_text}\n"
        article_dict["Abstract"] = abstract_text.strip() if abstract_text else ""

        # Extract Authors
        authors = []
        for author in article_element.findall(".//AuthorList/Author"):
            last_name = author.findtext("LastName") or ""
            fore_name = author.findtext("ForeName") or ""
            initials = author.findtext("Initials") or ""
            collective_name = author.findtext("CollectiveName")
            if collective_name:
                authors.append(collective_name)
            else:
                full_name = " ".join([fore_name, last_name]).strip()
                authors.append(full_name)
        article_dict["Authors"] = authors

        # Extract Publication Date
        pub_date = article_element.find(".//PubDate")
        if pub_date is not None:
            year = pub_date.findtext("Year")
            month = pub_date.findtext("Month")
            day = pub_date.findtext("Day")
            if year and month and day:
                try:
                    month_num = self._convert_month_to_number(month)
                    day_num = day.zfill(2)
                    article_dict["PublicationDate"] = f"{year}-{month_num}-{day_num}"
                except:
                    article_dict["PublicationDate"] = f"{year}-{month}-{day}"
            elif year and month:
                try:
                    month_num = self._convert_month_to_number(month)
                    article_dict["PublicationDate"] = f"{year}-{month_num}"
                except:
                    article_dict["PublicationDate"] = f"{year}-{month}"
            elif year:
                article_dict["PublicationDate"] = year
            else:
                article_dict["PublicationDate"] = "Unknown"
        else:
            article_dict["PublicationDate"] = "Unknown"

        # Extract Keywords
        keywords = []
        for keyword in article_element.findall(".//KeywordList/Keyword"):
            if keyword.text:
                keywords.append(keyword.text.strip())
        article_dict["Keywords"] = keywords

        # Extract Journal Information
        journal = article_element.find(".//Journal/Title")
        if journal is not None and journal.text:
            article_dict["Journal"] = journal.text.strip()
        else:
            article_dict["Journal"] = "Unknown"

        # Extract Article Sections (e.g., Methods, Conclusions)
        sections = {}
        for abstract_section in article_element.findall(".//Abstract/AbstractText"):
            label = abstract_section.get("Label")
            section_content = ''.join(abstract_section.itertext()).strip()
            if label and section_content:
                sections[label] = section_content
        if sections:
            article_dict.update(sections)

        # Extract Copyright Information
        copyright_info = article_element.find(".//CopyrightInformation")
        if copyright_info is not None and copyright_info.text:
            article_dict["Copyright"] = copyright_info.text.strip()
        else:
            article_dict["Copyright"] = "Unknown"

        return article_dict

    def _convert_month_to_number(self, month_str: str) -> str:
        """Convert month abbreviation or full name to a two-digit number."""
        import datetime
        try:
            datetime_obj = datetime.datetime.strptime(month_str[:3], '%b')
            return f"{datetime_obj.month:02}"
        except ValueError:
            return month_str  # Return as-is if it cannot be parsed


    def parse_pubmed_book_article(self, book_element: ET.Element) -> Dict[str, Any]:
        """Parse a PubmedBookArticle XML element into a dictionary with comprehensive fields."""
        book_dict = {}

        # Extract PMID
        book_dict["PMID"] = book_element.findtext(".//PMID")

        # Extract Book Title
        book_dict["BookTitle"] = book_element.findtext(".//BookTitle")

        # Extract Authors
        authors = []
        for author in book_element.findall(".//AuthorList/Author"):
            last_name = author.findtext("LastName") or ""
            fore_name = author.findtext("ForeName") or ""
            initials = author.findtext("Initials") or ""
            collective_name = author.findtext("CollectiveName")
            if collective_name:
                authors.append(collective_name)
            else:
                full_name = " ".join([fore_name, last_name]).strip()
                authors.append(full_name)
        book_dict["Authors"] = authors

        # Extract Publication Date
        pub_date = book_element.find(".//PubDate")
        if pub_date is not None:
            year = pub_date.findtext("Year")
            month = pub_date.findtext("Month")
            day = pub_date.findtext("Day")
            if year and month and day:
                try:
                    book_dict["PublicationDate"] = (
                        f"{year}-{month.zfill(2)}-{day.zfill(2)}"
                    )
                except:
                    book_dict["PublicationDate"] = f"{year}-{month}-{day}"
            elif year and month:
                book_dict["PublicationDate"] = f"{year}-{month}"
            elif year:
                book_dict["PublicationDate"] = year
            else:
                book_dict["PublicationDate"] = "Unknown"
        else:
            book_dict["PublicationDate"] = "Unknown"

        # Extract Keywords
        keywords = []
        for keyword in book_element.findall(".//KeywordList/Keyword"):
            if keyword.text:
                keywords.append(keyword.text.strip())
        book_dict["Keywords"] = keywords

        # Extract Publisher Information
        publisher = book_element.find(".//Publisher")
        if publisher is not None and publisher.text:
            book_dict["Publisher"] = publisher.text.strip()
        else:
            book_dict["Publisher"] = "Unknown"

        # Extract Copyright Information
        copyright_info = book_element.find(".//CopyrightInformation")
        if copyright_info is not None and copyright_info.text:
            book_dict["Copyright"] = copyright_info.text.strip()
        else:
            book_dict["Copyright"] = "Unknown"

        return book_dict

    def load_articles_by_date(
        self: object,
        base_query: str,
        start_date: str,
        end_date: str,
        max_results: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Load articles within a specific date range.

        Parameters:
            - base_query: The main search query.
            - start_date: Start date in YYYY/MM/DD format.
            - end_date: End date in YYYY/MM/DD format.
            - max_results: Maximum number of articles to retrieve.

        Returns:
            A list of article dictionaries.
        """
        # Convert string dates to datetime objects for manipulation
        start_dt = datetime.datetime.strptime(start_date, "%Y/%m/%d")
        end_dt = datetime.datetime.strptime(end_date, "%Y/%m/%d")

        def recursive_load(query, start, end, remaining):
            date_query = f'("{start.strftime("%Y/%m/%d")}"[PDAT] : "{end.strftime("%Y/%m/%d")}"[PDAT])'
            full_query = f"{query} AND {date_query}"
            search_results = self.search_with_history(full_query)
            total_available = search_results["count"]
            print(
                f"Total articles found for {start.strftime('%Y/%m/%d')} to {end.strftime('%Y/%m/%d')}: {total_available}"
            )

            if total_available == 0:
                return []

            # Determine how many articles to fetch in this range
            fetch_count = min(remaining, total_available, 9999)

            if fetch_count <= 9999:
                webenv = search_results["WebEnv"]
                query_key = search_results["QueryKey"]
                articles = self.fetch_articles(
                    webenv, query_key, batch_size=1000, max_results=fetch_count
                )

                
                #print("Articles in load_articles_by_date", articles, type(articles[0]))

                return articles
            else:
                # Split the date range into two halves
                mid_point = start + (end - start) / 2
                mid_point = mid_point.replace(hour=0, minute=0, second=0, microsecond=0)
                mid_date_str = mid_point.strftime("%Y/%m/%d")

                # Load first half
                first_half = recursive_load(query, start, mid_point, remaining)
                # Update remaining
                remaining_after_first = remaining - len(first_half)
                if remaining_after_first <= 0:
                    return first_half

                # Load second half
                second_half = recursive_load(
                    query, mid_point + timedelta(days=1), end, remaining_after_first
                )
                return first_half + second_half

        # Determine the total number of results to fetch
        if max_results is None:
            # If max_results is not specified, fetch all available articles
            # Note: Depending on the API's total limit, you might need to handle this differently
            max_results = float("inf")
        else:
            max_results = min(
                max_results, float("inf")
            )  # Adjust if there's an upper API limit

        # Start the recursive loading process
        articles = recursive_load(base_query, start_dt, end_dt, max_results)
        return articles


class ArticleLoader:
    """
    the ArticleLoader is the main class of this file, it uses the CustomPubMed 
    class to download the articles from PubMed. It is also build for threading
    concurrency. 
    Each downloading session gets its own Article loader which runs 
    load_articles in a thread
    """
    def __init__(self):
        self.lock = threading.Lock() # for threading
        self.progress = 0 # is can be read to check the progress of the download.
        self.total = 0 # will be set with the total number of available papers 
        self.articles = []
        self.status = "Idle"
        self.output_files = {}
        self.last_updated = time.time()

    def update_timestamp(self):
        with self.lock:
            self.last_updated = time.time()

    def load_articles(
        self, search_term: str, email: str, max_results: Optional[int] = None
    ):

        self.update_timestamp()

        def task():
            base_dir = f"../data/{uuid.uuid4()}"
            os.makedirs(base_dir, exist_ok=True)
            output_pickle = os.path.join(base_dir, "article_ids.pk")
            output_json = os.path.join(base_dir, "articles.json")
            output_txt = os.path.join(base_dir, "articles_txt")
            output_zip = os.path.join(base_dir, "articles.zip")

            with self.lock:
                self.output_files["json"] = output_json
                self.output_files["zip"] = output_zip

            pubmed = CustomPubMed(tool="PubMedSearcher", email=email)
            # Define initial date ranges (e.g., yearly)
            date_ranges = [
                ("1950/01/01", "1955/12/31"),
                ("1956/01/01", "1960/12/31"),
                ("1961/01/01", "1965/12/31"),
                ("1966/01/01", "1970/12/31"),
                ("1971/01/01", "1975/12/31"),
                ("1976/01/01", "1980/12/31"),
                ("1981/01/01", "1985/12/31"),
                ("1986/01/01", "1990/12/31"),
                ("1991/01/01", "1995/12/31"),
                ("1996/01/01", "2000/12/31"),
                ("2001/01/01", "2005/12/31"),
                ("2006/01/01", "2010/12/31"),
                ("2011/01/01", "2015/12/31"),
                ("2016/01/01", "2020/12/31"),
                ("2021/01/01", f"{datetime.datetime.now().year}/12/31"),
            ]

            # Preparing for batched download
            self.status = "Starting..."
            self.progress = 0
            self.articles = []

            all_articles = []
            total_fetched = 0
            search_results = pubmed.search_with_history(search_term)
            total_available = search_results["count"]
            with self.lock:
                self.total = max_results if max_results else total_available
                self.status = "Downloading..."

            for start_date, end_date in date_ranges:
                if max_results and total_fetched >= max_results:
                    break
                remaining = max_results - total_fetched if max_results else None
                print(f"\nProcessing date range: {start_date} to {end_date}")
                articles = pubmed.load_articles_by_date(
                    base_query=search_term,
                    start_date=start_date,
                    end_date=end_date,
                    max_results=remaining,
                )
                all_articles.extend(articles)
                total_fetched += len(articles)
                print(f"Total articles fetched so far: {total_fetched}")
                with self.lock:
                    self.progress = total_fetched
                if max_results and total_fetched >= max_results:
                    break

            # Save article IDs using pickle
            print("Saving Article ids using Pickle")

            with self.lock:
                self.status = "Save article IDs using pickle"

            article_ids = [article["PMID"] for article in all_articles]
            with open(output_pickle, "wb") as file:
                pk.dump(article_ids, file)
            print(f"Saved {len(article_ids)} article IDs to {output_pickle}")

            # Save articles to JSON
            print("Save Articles to json")

            with self.lock:
                self.status = "Save articles to JSON"

            with open(output_json, "w", encoding="utf-8") as json_file:
                json.dump(all_articles, json_file, indent=4)
            print(f"Saved articles to {output_json}")

            # Save articles to txt
            print("Save articles as txt files")
            with self.lock:
                self.status = "Save articles to txt"
            os.makedirs(output_txt, exist_ok=True)
            for i, article in enumerate(all_articles):
                json_to_txt(article, os.path.join(output_txt, f"{i}.txt"))

            # Create a zip archive of the txt directory only
            print("Creating Zip archive")
            with self.lock:
                self.status = "Creating ZIP archive"
            with zipfile.ZipFile(output_zip, "w") as zipf:
                # Add each txt file to the archive
                for root, _, files in os.walk(output_txt):
                    for file in files:
                        zipf.write(
                            os.path.join(root, file),
                            os.path.relpath(os.path.join(root, file), output_txt),
                        )

            print(f"Created zip archive {output_zip} containing all txt files.")

            with self.lock:
                self.status = "Completed"

        threading.Thread(target=task).start()

    def get_progress(self):

        self.update_timestamp()

        with self.lock:
            return {
                "status": self.status,
                "progress": self.progress,
                "total": self.total,
            }


if __name__=="__main__":
    loader = ArticleLoader()

    search_term = "(Brain) AND (glymph*)"   
    email = "beckers@time.rwth-aachen.de"
    max_results= 100

    # Start the loading process
    loader.load_articles(search_term, email, max_results)