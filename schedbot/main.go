package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"os"
	"strconv"
	"strings"
	"time"

	"github.com/go-redis/redis/v8"
	tg "github.com/go-telegram-bot-api/telegram-bot-api/v5"
	"github.com/google/uuid"
)

var (
	ctx = context.Background()
)

func mustEnv(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}

type ScheduleResult struct {
	RequestID   string `json:"request_id"`
	Status      string `json:"status"`
	Assignments []struct {
		StaffID int    `json:"staff_id"`
		Day     int    `json:"day"`
		Shift   string `json:"shift"`
	} `json:"assignments"`
}

func main() {
	// Load config from env
	token := os.Getenv("TELEGRAM_TOKEN")
	if token == "" {
		log.Fatal("TELEGRAM_TOKEN is required")
	}
	rHost := mustEnv("REDIS_HOST", "redis")
	rPort := mustEnv("REDIS_PORT", "6379")
	rDB, _ := strconv.Atoi(mustEnv("REDIS_DB", "0"))
	reqStream := mustEnv("REDIS_REQUEST_STREAM", "reschedule:trigger")
	resStream := mustEnv("REDIS_RESULT_STREAM", "schedule:results")
	rGroup := mustEnv("REDIS_CONSUMER_GROUP", "bot_consumer")

	// Initialize Redis client
	rdb := redis.NewClient(&redis.Options{
		Addr: rHost + ":" + rPort,
		DB:   rDB,
	})

	// Ensure consumer group exists for result stream
	if err := rdb.XGroupCreateMkStream(ctx, resStream, rGroup, "0").Err(); err != nil && !strings.Contains(err.Error(), "BUSYGROUP") {
		log.Fatalf("XGroupCreate error: %v", err)
	}

	// Initialize Telegram Bot
	bot, err := tg.NewBotAPI(token)
	if err != nil {
		log.Panic(err)
	}
	bot.Debug = false

	u := tg.NewUpdate(0)
	u.Timeout = 60
	updates := bot.GetUpdatesChan(u)

	// Goroutine: listen for scheduling results
	go func() {
		consumerName := uuid.NewString()
		for {
			entries, err := rdb.XReadGroup(ctx, &redis.XReadGroupArgs{
				Group:    rGroup,
				Consumer: consumerName,
				Streams:  []string{resStream, ">"},
				Count:    1,
				Block:    5 * time.Second,
			}).Result()
			if err != nil {
				if err == redis.Nil {
					continue
				}
				log.Printf("Error reading results: %v", err)
				continue
			}
			for _, stream := range entries {
				for _, message := range stream.Messages {
					raw, ok := message.Values["payload"].(string)
					if !ok {
						rdb.XAck(ctx, resStream, rGroup, message.ID)
						continue
					}
					var res ScheduleResult
					if err := json.Unmarshal([]byte(raw), &res); err != nil {
						log.Printf("Unmarshal result error: %v", err)
						rdb.XAck(ctx, resStream, rGroup, message.ID)
						continue
					}
					// Retrieve original doctor chat ID
					mapKey := "mapping:" + res.RequestID
					chatStr, err := rdb.Get(ctx, mapKey).Result()
					if err != nil {
						log.Printf("Mapping not found for request %s: %v", res.RequestID, err)
						rdb.XAck(ctx, resStream, rGroup, message.ID)
						continue
					}
					chatID, _ := strconv.ParseInt(chatStr, 10, 64)

					// Build schedule summary for this doctor
					var lines []string
					if res.Status == "success" {
						// Group assignments by day
						dayMap := make(map[int][]string)
						for _, a := range res.Assignments {
							if a.StaffID == int(chatID) {
								dayMap[a.Day] = append(dayMap[a.Day], a.Shift)
							}
						}
						lines = append(lines, "Ваш новый график на неделю:")
						for day := 0; day < 7; day++ {
							shifts, ok := dayMap[day]
							if !ok || len(shifts) == 0 {
								lines = append(lines, fmt.Sprintf("День %d: нет смен", day))
							} else {
								lines = append(lines, fmt.Sprintf("День %d: %s", day, strings.Join(shifts, ", ")))
							}
						}
					} else {
						lines = append(lines, "Не удалось пересоставить график. Пожалуйста, обратитесь к администратору.")
					}

					// Send message to doctor
					msgText := strings.Join(lines, "\n")
					bot.Send(tg.NewMessage(chatID, msgText))
					// Cleanup mapping
					rdb.Del(ctx, mapKey)
					rdb.XAck(ctx, resStream, rGroup, message.ID)
				}
			}
		}
	}()

	// Main loop: handle user commands
	for update := range updates {
		if update.Message == nil {
			continue
		}
		switch update.Message.Command() {
		case "reschedule":
			requestID := uuid.NewString()
			doctorID := update.Message.From.ID
			envelope := map[string]interface{}{
				"request_id": requestID,
				"doctor_id":  doctorID,
				"timestamp":  time.Now().UTC().Format(time.RFC3339),
				"reason":     "doctor_request",
			}
			data, _ := json.Marshal(envelope)
			if err := rdb.XAdd(ctx, &redis.XAddArgs{
				Stream: reqStream,
				Values: map[string]interface{}{"payload": string(data)},
			}).Err(); err != nil {
				bot.Send(tg.NewMessage(update.Message.Chat.ID, "Ошибка при отправке запроса. Попробуйте позже."))
				continue
			}
			// Store mapping for later notification
			rdb.Set(ctx, "mapping:"+requestID, strconv.FormatInt(update.Message.Chat.ID, 10), time.Hour)
			bot.Send(tg.NewMessage(update.Message.Chat.ID, "Запрос принят, ожидайте нового графика."))
		default:
			bot.Send(tg.NewMessage(update.Message.Chat.ID, "Неизвестная команда. Используйте /reschedule для пересчета графика."))
		}
	}
}
