FROM ubuntu:22.04

RUN apt-get update && apt-get install -y tor  \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /home/ting-client/
COPY . .

# Start Tor
RUN pip3 install stem
RUN pip3 install PySocks
RUN chmod +x run-ting.sh
CMD ["sh", "run-ting.sh"]
