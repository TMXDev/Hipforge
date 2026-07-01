# Use an official Node.js runtime as a parent image
FROM node:20-alpine

# Set the working directory in the container
WORKDIR /app

# Copy package.json and package-lock.json (if available)
COPY package*.json ./

# Handle empty package.json in pre-hackathon mode
RUN if [ ! -s package.json ]; then \
      echo '{"name": "frontend", "version": "1.0.0", "scripts": {"build": "echo build", "start": "node server.js"}}' > package.json && \
      echo "const http = require('http'); http.createServer((req, res) => res.end('ok')).listen(3000);" > server.js; \
    fi

# Install dependencies
RUN npm install

# Copy the rest of the application code
COPY . .

# Build the Next.js application
RUN npm run build

# Expose port 3000 for the Next.js app
EXPOSE 3000

# Start the Next.js application
CMD ["npm", "start"]
