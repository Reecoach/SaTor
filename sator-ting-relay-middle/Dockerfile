FROM ubuntu:22.04

RUN apt-get update && apt-get install -y \
    apt-transport-https \
    wget \
    gnupg \
    lsb-release \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /home/SaTor-Ting/
COPY . .

RUN chmod +x run_middle_relay.sh

# Configure and Start Tor
CMD ["/bin/bash", "run_middle_relay.sh"]
