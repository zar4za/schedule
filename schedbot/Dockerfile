# Build the Go Telegram bot
FROM golang:1.24-alpine AS builder
WORKDIR /app

# Cache dependencies
COPY go.mod go.sum ./
RUN go mod download

# Copy source code and build
COPY . ./
RUN go build -o bot ./main.go

# Final minimal image
FROM alpine:3.18
RUN apk add --no-cache ca-certificates
WORKDIR /app
COPY --from=builder /app/bot ./bot

# Configuration via environment variables
ENV TELEGRAM_TOKEN=""
ENV REDIS_HOST="redis"
ENV REDIS_PORT="6379"
ENV REDIS_DB="0"
ENV REDIS_REQUEST_STREAM="reschedule:trigger"
ENV REDIS_RESULT_STREAM="schedule:results"
ENV REDIS_CONSUMER_GROUP="bot_consumer"

ENTRYPOINT ["/app/bot"]