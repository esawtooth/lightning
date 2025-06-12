FROM rust:1.72-slim AS build
WORKDIR /app
COPY context-hub/ ./
RUN cargo build --release

FROM debian:bullseye-slim
WORKDIR /app
COPY --from=build /app/target/release/context-hub /usr/local/bin/context-hub
EXPOSE 3000
ENTRYPOINT ["context-hub"]
