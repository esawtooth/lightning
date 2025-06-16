FROM --platform=linux/amd64 rust:1.87-slim AS build
WORKDIR /app
COPY . ./
RUN rustup target add x86_64-unknown-linux-musl \
    && cargo build --release --target x86_64-unknown-linux-musl

FROM --platform=linux/amd64 debian:bookworm-slim
RUN apt-get update && apt-get install -y \
    ca-certificates \
    libssl3 \
    && rm -rf /var/lib/apt/lists/*

# Create a working directory with proper permissions
WORKDIR /hub
RUN mkdir -p /hub/data /hub/snapshots /hub/index /hub/blobs && \
    chmod 755 /hub /hub/data /hub/snapshots /hub/index /hub/blobs

COPY --from=build /app/target/x86_64-unknown-linux-musl/release/context-hub /usr/local/bin/context-hub

# Set environment variables to use the pre-created directories
ENV DATA_DIR=/hub/data
ENV SNAPSHOT_DIR=/hub/snapshots
ENV INDEX_DIR=/hub/index
ENV BLOB_DIR=/hub/blobs

EXPOSE 3000
ENTRYPOINT ["context-hub"]
