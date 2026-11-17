# pigu-feed — Play with me → Pigu (PMP)

Автоматический XML-фид товаров для Pigu / Kaup24 / 220.lv / Hobbyhall.

**Как это работает:** вы отправляете EAN Telegram-боту → GitHub Actions каждые ~5–15 минут
забирает сообщения → Claude ищет товар в интернете, выбирает категорию Pigu, пишет названия
и описания на 6 языках (lt, lv, ee, fi, ru, en) и заполняет атрибуты → фото скачиваются,
приводятся к требованиям Pigu (белый квадрат 1000–2000 px, JPG) и публикуются на GitHub Pages →
собирается `docs/feed.xml` → Pigu сам забирает фид по ссылке.

- Фид для PMP: `https://iljakurguzov.github.io/pigu-feed/feed.xml`
- Список товаров: `https://iljakurguzov.github.io/pigu-feed/`

## Настройка (один раз)

1. **Secrets** (Settings → Secrets and variables → Actions):
   - `ANTHROPIC_API_KEY` — ключ Claude API
   - `TELEGRAM_BOT_TOKEN` — токен бота от @BotFather
   - `TELEGRAM_ALLOWED_CHAT_ID` — необязательно; без него владельцем станет первый, кто напишет боту
2. **Claude Console**: включите Web search для организации (Settings → Privacy/Capabilities), пополните баланс.
3. **Pages**: Settings → Pages → Deploy from a branch → `main` / `/docs`.
4. **Actions**: вкладка Actions → `pigu-feed` → Run workflow (первый запуск вручную).
5. Напишите боту `/start`.
6. **PMP**: Products → Import → Products import (XML) → вставить ссылку на фид.
   Затем Products → Import → Supplier categories mapping — сопоставить каждую категорию
   (в фиде категории названы как в Pigu, напр. `Toys / Puzzles`).

## Команды бота

| | |
|---|---|
| EAN (один или много) | добавить товары |
| фото штрихкода | распознать и добавить |
| .txt / .csv со списком EAN | массовая загрузка |
| фото с подписью EAN | добавить своё фото к товару |
| `/status`, `/list`, `/info EAN` | обзор |
| `/set EAN weight 0.45` | вес кг; `length`/`height`/`width` в метрах |
| `/set EAN category 10669` | другая категория Pigu (тексты перепишутся) |
| `/set EAN manufacturer Имя \| Адрес \| e-mail` | производитель; `rep` — представитель в ЕС |
| `/set EAN sku MY-CODE` | свой артикул (по умолчанию `PWM-<EAN>`) |
| `/redo EAN`, `/delete EAN` | найти заново / убрать из фида |

## Правила, которые соблюдает генератор

- весь текст в CDATA, порядок тегов как в шаблоне Pigu;
- один цвет = один `<product>`, одна модификация на EAN;
- если размеры/вес неизвестны — 0.1 (м / кг), бот об этом сообщает;
- товар не попадает в фид, если нет категории, названия, описания или фото;
- атрибуты — литовские названия полей и только допустимые значения из `data/categories.json`.

Обновить категории: `python tools/convert_categories.py Categories_fields_and_values.xlsx`.

Данные товаров: `data/products.json` (можно править вручную, фид пересоберётся при следующем запуске).
