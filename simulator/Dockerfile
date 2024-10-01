FROM ubuntu:22.04

RUN apt-get update && apt-get install -y python3  \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /home/sator-simulator/
COPY . .

# Start Tor
RUN chmod +x run-simulator.sh
CMD ["sh", "run-simulator.sh"]

