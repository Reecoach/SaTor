FROM ubuntu:22.04

RUN apt-get update && apt-get install -y tor  \
    python3  \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /home/sator-ting-client/
COPY . .

# Start Tor
RUN chmod +x run-client.sh
CMD ["sh", "run-client.sh"]

