# Фамильное древо

Простой сайт семейного древа: одна HTML-страница и один файл данных. Без сборки, без базы, без зависимостей.

Живой пример: https://family.victor-komlev.ru

## Как развернуть своё древо

1. Скопируйте папку `site/` (или сделайте форк репозитория).
2. Замените `site/people.json` своими данными (в репозитории — вымышленный пример), фото положите в `site/photos/`.
3. Проверьте локально:
   ```bash
   cd site && python -m http.server 8000
   ```
   и откройте http://localhost:8000
4. Выложите содержимое `site/` на любой статический хостинг: свой сервер с nginx, GitHub Pages, Netlify.

## Формат `people.json`

```json
{
  "meta": {"title": "Древо семьи", "root": "id-корня", "hideLiving": true},
  "captions": {"photos/файл.jpg": "Подпись к фото: кто, где, когда"},
  "people": [
    {
      "id": "ivanov-ivan",
      "surname": "Иванов", "name": "Иван", "patronymic": "Петрович",
      "maiden": "девичья фамилия (для женщин)",
      "sex": "m",
      "living": false,
      "birth": {"date": "1900-01-31", "place": "с. Такое-то"},
      "death": {"date": "~1970", "place": "", "cause": ""},
      "father": "id отца", "mother": "id матери",
      "spouses": [{"id": "id супруги", "date": "1925", "place": ""}],
      "notes": "свободный текст",
      "sources": ["метрическая книга …"],
      "photos": ["photos/файл.jpg"]
    }
  ]
}
```

- Даты: `ГГГГ-ММ-ДД`, или просто год, или `~1850` для примерной.
- Дети и братья/сёстры вычисляются сами по полям `father`/`mother`.
- `living: true` + `meta.hideLiving: true` — даты живых людей на сайте не показываются.

## Справочник

`python tools/build_reference.py [путь/к/people.json]` собирает `docs/reference.md` — читаемый список всех людей по фамилиям.
