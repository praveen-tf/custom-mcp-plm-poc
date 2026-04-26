FROM mcr.microsoft.com/devcontainers/universal

# Remove the problematic yarn repository before features are installed
RUN rm -f /etc/apt/sources.list.d/yarn.list && \
    apt-get update
