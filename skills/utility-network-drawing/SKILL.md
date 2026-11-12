---
name: utility-network-drawing
description: Use when turning a hand-drawn heat/gas network sketch (JPG/PNG/PDF scan) into an editable DWG/PDF/PNG with NetSketch, when authoring or fixing model.json for such a sketch, or when debugging scale, layout, symbols and titles of the generated sheet.
---

# NetSketch: эскиз сети → редактируемый DWG

Проект `utility-network-recreation` превращает рукописный эскиз тепловой или
газовой сети в лист с рамкой, штампом, легендой, спецификацией и примечаниями.
Внутри два независимых слоя:

1. **Понимание** — модель зрения отдаёт `model.json` (семантику трассы).
2. **Черчение** — детерминированный движок строит DXF → DWG, PDF, PNG.

Модель не рисует линии «руками» и не вызывает CAD-команды: это даёт
повторяемость и лишает её возможности испортить геометрию.

## Когда применять

* Пользователь даёт скан/фото эскиза и просит чертёж в DWG (или PDF/PNG).
* Нужно разобрать эскиз в структуру (`model.json`) для последующей сборки.
* Чертёж собрался, но «не похож»: не тот масштаб, наложения текста, пустой план.
* Нужно добавить новый тип сети или новое условное обозначение.

## Быстрый старт

```powershell
# зависимости один раз (в папку проекта, системный Python не трогаем)
python -m pip install --target .pydeps -r requirements.txt
$env:PYTHONPATH = "$PWD\.pydeps"

python -m netsketch doctor           # что настроено: OCS, модель, библиотеки
python -m netsketch serve            # веб-интерфейс на 127.0.0.1:8770
```

Готовый чертёж из модели:

```powershell
python -m netsketch build examples\gas\02\model.json --out output --stem gas02
```

## Рабочий цикл руками (когда LLM не настроен)

1. `python -m netsketch serve` → в интерфейсе создать задачу с эскизом.
   Задача встанет в `waiting_agent`, в `data/jobs/<id>/` появятся
   `prompt_system.txt`, `prompt_user.txt` и `input/`.
2. Прочитать эскиз (vision) и написать `data/jobs/<id>/model.json`
   по схеме `references/model-schema.md`.
3. Отправить модель: `POST /api/jobs/<id>/model` с JSON — или положить файл
   и нажать «Повторить».
4. Проверить результат по `references/qa-checklist.md`, отдать DWG/PDF/PNG.

## Главные правила

* **Ничего не выдумывать молча.** Всё домысленное — в `assumptions`, слой
  `ASSUMED`, отдельная пометка на листе.
* **Координаты — в пикселях эскиза, Y вниз.** Перевод в мм делает раскладка.
* **Масштаб.** Если есть таблица длин — `mm_per_px` считается по ней
  (DERIVED). Если нет — масштаб условный (ASSUMED), это видно в примечаниях.
* **Диаметры** — целые мм. **Длины** — мм (`length_mm`), в спецификации — м.
* Один диаметр подписывается один раз на цепочку одинаковых участков.
* Если подпись не читается — не угадывать, а писать в `warnings`.

## Что где лежит

```
netsketch/model.py      схема модели, терпимый разбор, нормализация типов
netsketch/layout.py     раскладка листа: масштаб, план, легенда, таблицы
netsketch/symbols.py    условные обозначения (valve, filter, well, gpsh…)
netsketch/sheets.py     форматы, рамка, основная надпись 185×55
netsketch/dxfout.py     сцена → DXF (ezdxf)
netsketch/render.py     сцена → PDF/PNG (matplotlib)
netsketch/dwg.py        DXF → DWG через Open CAD Studio `--export`
netsketch/recognize.py  вызов модели зрения + разбор JSON
knowledge/                  тексты для промпта и людей
examples/               пары «эскиз → ваш DWG»
```

## Диагностика

| Симптом | Причина | Что делать |
|---|---|---|
| План пустой, рамка есть | масштаб/координаты вне листа | смотреть `transform`, `mm_per_px`; собрать с `--scale 500` |
| Всё в углу, мелко | `mm_per_px` завышен | убрать `mm_per_px`, дать длину в `specification` |
| DWG не создан | нет Open CAD Studio | `python -m netsketch doctor`, задать `NS_OCS_EXE` |
| Задача висит в `waiting_agent` | нет ключа модели | `.env` с vision-моделью или ручной `model.json` |
| Текст наезжает | слишком длинная подпись | сократить `labels[].text`, поднять `height`/`offset` |
| PDF пустой | не тот масштаб печати | PDF строится рендером 1:1, проверять PNG |

## Проверка перед выдачей

`python tools/smoke_test.py` — прогоняет сборку, читает DWG обратно,
сверяет размер PDF с листом. Всё зелёное — можно отдавать.

