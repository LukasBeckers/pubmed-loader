// frontend/src/components/ArticleLoader.jsx

import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:5000/api"

const ArticleLoader = () => {
  const [searchTerm, setSearchTerm] = useState('');
  const [email, setEmail] = useState('');
  const [maxResults, setMaxResults] = useState('');
  const [status, setStatus] = useState('');
  const [progress, setProgress] = useState(0);
  const [total, setTotal] = useState(0);
  const intervalRef = useRef(null);
  const [jsonAvailable, setJsonAvailable] = useState(false);
  const [zipAvailable, setZipAvailable] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [loaderId, setLoaderId] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (isLoading) return;

    setIsLoading(true);

    // Reset states
    setStatus('');
    setProgress(0);
    setTotal(0);
    setJsonAvailable(false);
    setZipAvailable(false);
    setLoaderId('');

    try {
      console.log("Api base url", API_BASE_URL)
      const response = await axios.post(`${API_BASE_URL}/start`, {
        search_term: searchTerm,
        email: email,
        max_results: maxResults
      });

      if (response.data.loader_id) {
        console.log("response loader_id", response.data.loader_id);
        setLoaderId(response.data.loader_id);
        setStatus('Loading started');
      } else {
        setStatus("Error starting the loading process (no loader_id)");
        setIsLoading(false);
      }
    } catch (error) {
      console.error(error);
      setStatus('Error starting the loading process');
      setIsLoading(false);
    };
  };

  const fetchStatus = async () => {
    try {
      console.log("Loader ID", loaderId)
      const response = await axios.get(`${API_BASE_URL}/status`, { params: { loader_id: loaderId } });
      console.log("Status abfrage", response.data.status, response.data.progress, response.data.total)
      setStatus(response.data.status);
      setProgress(response.data.progress);
      setTotal(response.data.total);

      if (response.data.status === 'Completed' || response.data.status.startsWith('Error')) {
        if (intervalRef.current) {
          clearInterval(intervalRef.current);
          intervalRef.current = null;
        }
        if (response.data.status === "Completed") {
          setJsonAvailable(true);
          setZipAvailable(true);
          setIsLoading(false);
        }
        else {
          setIsLoading(false);
        }
      }
    }
    catch (error) {
      console.error(error);
      setStatus('Error during the loading process');
      setIsLoading(false);
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    }
  };

  useEffect(() => {
    if (loaderId) {
      console.log("Starting status fetch for loader_id:", loaderId);

      // Clear any existing interval before starting a new one
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }


      //starting poll for status
      intervalRef.current = setInterval(fetchStatus, 500);

      // Cleanup on unmount
      return () => {
        if (intervalRef.current) {
          intervalRef.current = null;
        }
      };
    }
  }, [loaderId]);

  return (
    <div style={styles.container}>
      <h2>Article Loader</h2>
      <form onSubmit={handleSubmit} style={styles.form}>
        <div style={styles.inputGroup}>
          <label>Search Term:</label>
          <input
            type="text"
            value={searchTerm}
            required
            onChange={(e) => setSearchTerm(e.target.value)}
            style={styles.input}
          />
        </div>
        <div style={styles.inputGroup}>
          <label>Email:</label>
          <input
            type="email"
            value={email}
            required
            onChange={(e) => setEmail(e.target.value)}
            style={styles.input}
          />
        </div>
        <div style={styles.inputGroup}>
          <label>Max Results:</label>
          <input
            type="number"
            value={maxResults}
            onChange={(e) => setMaxResults(e.target.value)}
            placeholder="Optional"
            style={styles.input}
          />
        </div>
        <button type="submit" style={styles.button} disabled={isLoading}>{isLoading ? 'Loading ...' : 'Start Loading'}</button>
      </form>

      {status && (
        <div style={styles.statusContainer}>
          <h3>Status: {status}</h3>
          {total > 0 && (
            <div>
              <progress value={progress} max={total} style={styles.progress}></progress>
              <p>{progress} / {total} articles loaded</p>
            </div>
          )}
        </div>
      )}

      {jsonAvailable && (
        <a
          href={`${API_BASE_URL}/download/json?loader_id=${loaderId}`}
          download
        >
          <button style={styles.downloadButton}>Download JSON</button>
        </a>
      )}
      {zipAvailable && (
        <a
          href={`${API_BASE_URL}/download/zip?loader_id=${loaderId}`}
          download
        >
          <button style={styles.downloadButton}>Download ZIP</button>
        </a>
      )}
    </div>
  );
};

// Inline CSS styles for simplicity
const styles = {
  container: {
    maxWidth: '600px',
    margin: 'auto',
    padding: '20px',
    fontFamily: 'Arial, sans-serif'
  },
  form: {
    display: 'flex',
    flexDirection: 'column'
  },
  inputGroup: {
    marginBottom: '15px'
  },
  input: {
    width: '100%',
    padding: '8px',
    marginTop: '5px',
    boxSizing: 'border-box'
  },
  button: {
    padding: '10px 20px',
    cursor: 'pointer',
    backgroundColor: '#4CAF50',
    color: 'white',
    border: 'none',
    borderRadius: '4px'
  },
  statusContainer: {
    marginTop: '20px'
  },
  progress: {
    width: '100%',
    height: '20px'
  },
  downloadContainer: {
    marginTop: '20px'
  },
  downloadButton: {
    padding: '10px 20px',
    marginRight: '10px',
    cursor: 'pointer',
    backgroundColor: '#008CBA',
    color: 'white',
    border: 'none',
    borderRadius: '4px'
  }
};

export default ArticleLoader;
