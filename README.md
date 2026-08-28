# Invoice Generator for Codex

[![CI](https://github.com/gleero/codex-invoice-generator/actions/workflows/ci.yml/badge.svg)](https://github.com/gleero/codex-invoice-generator/actions/workflows/ci.yml)
[![CodeQL](https://github.com/gleero/codex-invoice-generator/actions/workflows/codeql.yml/badge.svg)](https://github.com/gleero/codex-invoice-generator/actions/workflows/codeql.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Навык для Codex, который сам создаёт одностраничные PDF-инвойсы, хранит реквизиты клиентов в Markdown и ведёт отдельную нумерацию для каждой компании.

Код навыка и ваши документы хранятся раздельно:

```text
~/.agents/skills/invoice-generator/   <- код, шрифты и .venv
~/Documents/My Invoices/              <- ваши реквизиты, клиенты и PDF
```

В рабочую папку не копируются Python-код, зависимости или виртуальное окружение.

## Что понадобится

- macOS, Linux или Windows;
- [Python 3.11 или новее](https://www.python.org/downloads/);
- Codex desktop, Codex CLI или расширение Codex;
- доступ к [GitHub-репозиторию](https://github.com/gleero/codex-invoice-generator).

## Установка: macOS или Linux

Откройте Terminal и выполните две команды:

```bash
mkdir -p "$HOME/.agents/skills"
git clone https://github.com/gleero/codex-invoice-generator.git "$HOME/.agents/skills/invoice-generator"
```

Полностью перезапустите Codex. Персональные навыки из `$HOME/.agents/skills` поддерживаются официально; если новый навык не появился сразу, документация рекомендует перезапуск. [OpenAI Codex Skills](https://developers.openai.com/codex/skills)

## Установка: Windows PowerShell

```powershell
New-Item -ItemType Directory -Force "$HOME\.agents\skills" | Out-Null
git clone https://github.com/gleero/codex-invoice-generator.git "$HOME\.agents\skills\invoice-generator"
```

После клонирования полностью перезапустите Codex.

## Создание рабочей папки

1. Создайте обычную папку, например `Documents/My Invoices`.
2. Откройте именно эту папку в Codex как рабочую.
3. Ничего вручную не устанавливайте и не запускайте.
4. Сразу напишите запрос, например:

   > Выставь инвойс компании Example Ltd на 1500 евро за разработку сайта.

Если папка ещё не настроена, Codex ответит примерно так:

> В этой папке ещё нет Invoice Generator workspace. Инициализировать её здесь?

Если папка не пустая, Codex перечислит найденные файлы и отдельно предупредит об этом. Пока вы не ответите «да», навык ничего не создаст и не будет устанавливать зависимости.

После согласия Codex:

1. создаст собственную `.venv` внутри установленного навыка;
2. создаст в рабочей папке `.invoice-gen`, `data/` и `output/`;
3. сначала спросит ваши банковские счета и валюты;
4. затем спросит имя, юридический статус, адрес и timezone;
5. продолжит первоначальный запрос на инвойс.

На установку Python-пакетов Codex может один раз запросить системное разрешение и доступ в интернет.

## Пример первого запуска целиком

Ничего из команд ниже вручную выполнять не нужно. Обычный диалог выглядит так:

> **Пользователь:** Выставь инвойс компании Example Company Ltd на 1500 евро за разработку сайта.
>
> **Codex:** В этой папке ещё нет Invoice Generator workspace. Инициализировать её здесь? Папка не пустая: `notes.md` уже существует. Я добавлю только `.invoice-gen`, `.gitignore`, `data/` и `output/`.
>
> **Пользователь:** Да.
>
> **Codex:** Какие валюты вы принимаете? Для каждой пришлите банковские строки так, как они должны попасть в PDF. Нужна хотя бы одна валюта.
>
> **Пользователь:** EUR. Beneficiary Bank: Example Bank; Beneficiary: JANE EXAMPLE; Account: XX00EXAMPLE.
>
> **Codex:** Теперь нужны ваш юридический статус, имя, рабочий адрес и timezone, например `Asia/Tbilisi`.
>
> **Пользователь:** Individual Entrepreneur, Jane Example, 1 Example Street, Tbilisi, Georgia, Asia/Tbilisi.
>
> **Codex:** Для клиента не хватает официального адреса.
>
> **Пользователь:** 10 Sample Road, London, United Kingdom. Company Number: 00000001.
>
> **Codex:** Предлагаю постоянный алиас `EC`. Подходит?
>
> **Пользователь:** Да.
>
> **Codex:** Первый новый инвойс будет `001`? Если нет, назовите стартовый номер.
>
> **Пользователь:** Да, с `001`.
>
> **Codex:** Готово: [EC-001.pdf](output/Example%20Company%20Ltd/EC-001.pdf).

В следующих запросах Codex увидит `.invoice-gen`, адресно проверит только изменившиеся Markdown-файлы и сразу продолжит выпуск. Повторять настройку не придётся.

## Первый клиент

Для новой компании Codex:

1. приводит присланные реквизиты к нормальной структуре, не выдумывая отсутствующие значения;
2. предлагает алиас из 2-3 букв, например `EC`;
3. спрашивает, подходит ли алиас;
4. спрашивает, будет ли первый новый инвойс `001`, или нужно начать с другого номера;
5. сохраняет клиента только после этих ответов.

После первого инвойса алиас и стартовая нумерация считаются постоянными.

## Где лежат данные

```text
My Invoices/
|-- .invoice-gen          служебный кэш состояния, без реквизитов
|-- .gitignore            защищает приватные файлы от случайного commit
|-- data/
|   |-- owner.md          ваши данные и счета
|   |-- clients/          по одному MD-файлу на клиента
|   `-- invoices.md       журнал выданных инвойсов
`-- output/
    `-- Example Ltd/
        `-- EC-001.pdf
```

Удаление или обновление навыка не удаляет рабочую папку. Не отправляйте `data/` и `output/` в публичный Git-репозиторий.

## Обычные запросы

```text
Выставь WG инвойс на $2000 за software development за август.

Добавь нового клиента. Вот реквизиты: ...

Проверь базу клиентов и нумерацию.

Добавь мне счёт в GEL. Хочу показывать сумму со знаком ₾ после числа.
```

Если суммы, валюты или деятельности не хватает, Codex спросит только недостающее. Когда всё собрано, отдельного вопроса «точно генерировать?» не будет.

## Обновление

```bash
git -C "$HOME/.agents/skills/invoice-generator" pull
```

При следующем запросе лаунчер заметит изменение зависимостей и при необходимости обновит свою `.venv`. Рабочая папка останется на месте.

## Удаление

Удалите только `~/.agents/skills/invoice-generator` и перезапустите Codex. Папка с MD и PDF не затрагивается.

## Если что-то не работает

### Codex не видит навык

Проверьте, что существует файл:

```text
~/.agents/skills/invoice-generator/SKILL.md
```

Затем полностью перезапустите Codex.

### Сообщение про Python

Установите Python 3.11+ с [python.org](https://www.python.org/downloads/), закройте и снова откройте Codex.

### Вы открыли не ту папку

Не соглашайтесь на инициализацию. Откройте нужную папку в Codex и повторите запрос.

### `.invoice-gen` повреждён

Попросите: «Почини маркер Invoice Generator в этой папке». Навык сначала запросит подтверждение, сохранит резервную копию и пересоберёт кэш из Markdown.

### Инвойс не помещается на страницу

Генератор не обрезает текст. Он укажет слишком длинное поле; сократите его и повторите запрос.

## CLI для продвинутых

Все команды по умолчанию используют текущую папку:

```bash
python3 ~/.agents/skills/invoice-generator/scripts/invoice.py probe --workspace "$PWD"

python3 ~/.agents/skills/invoice-generator/scripts/invoice.py \
  --workspace "$PWD" workspace status --json

python3 ~/.agents/skills/invoice-generator/scripts/invoice.py \
  --workspace "$PWD" issue --client EC --amount 1500 --currency EUR \
  --description "Software development services"
```

Команда `probe` не создаёт окружение и ничего не записывает.

## Разработка

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.lock
.venv/bin/python -m pip install --no-deps -e .
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/pyright
.venv/bin/pytest --cov=invoice_generator --cov-branch --cov-fail-under=90
.venv/bin/python scripts/validate_skill.py .
npm ci
npm run lint:md
```

Локальные reference PDF можно проверить через `scripts/compare_references.py`; они намеренно исключены из Git.

### Версионирование

Версия хранится в `pyproject.toml` и синхронно обновляется в Python-модуле и npm metadata:

```bash
.venv/bin/bump-my-version show current_version
.venv/bin/bump-my-version bump patch
.venv/bin/bump-my-version bump minor
.venv/bin/bump-my-version bump major
```

Команда изменяет файлы, но намеренно не создаёт commit или Git tag. Перед релизом проверьте diff, запустите тесты и отдельно создайте commit/tag.

## Лицензия

Код распространяется по лицензии MIT. Встроенные шрифты имеют собственные уведомления и OFL-лицензию в `assets/fonts/`.
