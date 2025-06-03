// File: main.go
package main

import (
	"fmt"
	"log"
	"math/rand"
	"os"
	"regexp"
	"strings"
	"time"

	tg "github.com/go-telegram-bot-api/telegram-bot-api/v5"
)

func main() {
	token := os.Getenv("TELEGRAM_TOKEN")
	if token == "" {
		log.Fatal("TELEGRAM_TOKEN is required")
	}

	bot, err := tg.NewBotAPI(token)
	if err != nil {
		log.Panic(err)
	}
	bot.Debug = false

	u := tg.NewUpdate(0)
	u.Timeout = 60
	updates := bot.GetUpdatesChan(u)

	rand.Seed(time.Now().UnixNano())
	shifts := []string{"morning", "day", "evening"}

	// Regex to parse /unavailable command: /unavailable YYYY-MM-DD YYYY-MM-DD
	reUnavailable := regexp.MustCompile(`^/unavailable\s+(\d{4}-\d{2}-\d{2})\s+(\d{4}-\d{2}-\d{2})`)

	for update := range updates {
		if update.Message == nil {
			continue
		}

		text := update.Message.Text
		chatID := update.Message.Chat.ID

		switch {
		case update.Message.IsCommand() && update.Message.Command() == "start":
			msg := tg.NewMessage(chatID, "Welcome to the ScheduleBot placeholder! Use /reschedule to get a mock schedule, /unavailable to set your unavailable dates.")
			bot.Send(msg)

		case update.Message.IsCommand() && update.Message.Command() == "reschedule":
			ack := tg.NewMessage(chatID, "Запрос на пересчет принят. Генерирую новый график...")
			bot.Send(ack)

			go func(chatID int64) {
				time.Sleep(time.Duration(3+rand.Intn(3)) * time.Second)
				var lines []string
				lines = append(lines, "Ваш новый график на неделю:")
				for day := 1; day <= 7; day++ {
					shift := shifts[rand.Intn(len(shifts))]
					lines = append(lines, fmt.Sprintf("День %d: %s", day, shift))
				}
				bot.Send(tg.NewMessage(chatID, strings.Join(lines, "\n")))
			}(chatID)

		case reUnavailable.MatchString(text):
			parts := reUnavailable.FindStringSubmatch(text)
			from := parts[1]
			to := parts[2]
			// For placeholder, we just acknowledge
			resp := fmt.Sprintf("Ваш период недоступности с %s по %s записан.", from, to)
			bot.Send(tg.NewMessage(chatID, resp))

		default:
			help := "Неизвестная команда. Доступные команды:\n" +
				"/start - приветствие\n" +
				"/reschedule - получить макет нового графика\n" +
				"/unavailable YYYY-MM-DD YYYY-MM-DD - задать период недоступности"
			bot.Send(tg.NewMessage(chatID, help))
		}
	}
}
