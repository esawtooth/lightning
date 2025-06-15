FROM rust:latest AS build
WORKDIR /app
COPY context-hub/ ./
RUN cargo build --release

FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y \
    ca-certificates \
    libssl3 \
    && rm -rf /var/lib/apt/lists/*

# Create a working directory with proper permissions
WORKDIR /hub
RUN mkdir -p /hub/data /hub/snapshots /hub/index /hub/blobs && \
    chmod 755 /hub /hub/data /hub/snapshots /hub/index /hub/blobs

COPY --from=build /app/target/release/context-hub /usr/local/bin/context-hub

# Set environment variables to use the pre-created directories
ENV DATA_DIR=/hub/data
ENV SNAPSHOT_DIR=/hub/snapshots
ENV INDEX_DIR=/hub/index
ENV BLOB_DIR=/hub/blobs

EXPOSE 3000
ENTRYPOINT ["context-hub"]
