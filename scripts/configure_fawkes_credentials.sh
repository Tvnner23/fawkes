#!/usr/bin/env bash
set -euo pipefail

config=/home/tvnner/.config/fawkes
install -d -m 0700 "$config"
read -rsp 'Fawkes app token: ' app_token; printf '\n'
read -rsp 'OpenAI API key: ' openai_key; printf '\n'
read -rsp 'Discord bot token: ' discord_token; printf '\n'
read -rp 'Tanner Discord user ID: ' tanner_id
read -rsp 'Discord failure-notification webhook URL: ' webhook_url; printf '\n'
umask 077
for value in "$app_token" "$openai_key" "$discord_token" "$tanner_id" "$webhook_url"; do
  [[ "$value" != *$'\n'* && "$value" != *$'\r'* ]] || { echo 'Credential values cannot contain newlines.' >&2; exit 2; }
done
printf 'FAWKES_APP_TOKEN=%s\nOPENAI_API_KEY=%s\n' "$app_token" "$openai_key" > "$config/app.env"
printf 'FAWKES_DISCORD_BOT_TOKEN=%s\nFAWKES_DISCORD_TANNER_USER_ID=%s\nOPENAI_API_KEY=%s\n' "$discord_token" "$tanner_id" "$openai_key" > "$config/discord-bot.env"
printf 'FAWKES_DISCORD_WEBHOOK_URL=%s\n' "$webhook_url" > "$config/notification.env"
chmod 0600 "$config"/*.env
unset app_token openai_key discord_token tanner_id webhook_url
echo 'Protected Fawkes credential files written.'
