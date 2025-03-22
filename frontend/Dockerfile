# Stage 1: Build the React application
FROM node:18-alpine AS build

# Set work directory
WORKDIR /app

# Declare build arguments
ARG VITE_API_BASE_URL
ARG SERVE_PORT

# Set environment variables using build arguments
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
ENV SERVE_PORT=${SERVE_PORT}

# Copy package.json and package-lock.json
COPY package*.json ./

# Install dependencies
RUN npm install

# Copy the rest of the project files
COPY . .

# Build the project
RUN npm run build

# Stage 2: Serve the built app with a Node server (No Nginx)
FROM node:18-alpine

# Declare build arguments
ARG VITE_API_BASE_URL
ARG SERVE_PORT

# Set environment variables using build arguments
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
ENV SERVE_PORT=${SERVE_PORT}

# Install serve globally
RUN npm install -g serve

# Set work directory
WORKDIR /app

# Copy the dist output from the previous stage
COPY --from=build /app/dist /app/dist

# Expose the frontend port
EXPOSE ${SERVE_PORT}

# Start the application using serve
CMD serve -s dist -l ${SERVE_PORT}
