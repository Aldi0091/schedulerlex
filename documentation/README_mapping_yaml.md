# mapping.yaml — Configuration Guide (for CSV A)

This file defines how **invoice line items are categorized** for CSV A.  
The script `csv_a.py` reads this file and assigns each line item to a category based on keyword matching.

---

## File purpose

`mapping.yaml` controls:

- which categories exist
- how line items are classified
- what happens if nothing matches

The script reads line item text and assigns it to the **first matching category**.

---

## File structure

Example:

```yaml
default_category: Unmapped

categories:
  - name: Rental
    label: "VERMIETUNG"
    keywords:
      - "miete"
      - "vermietung"
      - "rental"
```

---

## Fields explained

### `default_category`
Used when no keyword matches.

Example:
```yaml
default_category: Unmapped
```

If a line item does not match any rule → it goes to this category.

---

### `categories`
List of category rules.

Each category contains:

| Field | Required | Used by script | Description |
|------|-----------|----------------|-------------|
name | yes | yes | Category name written to CSV |
label | no | no | For human reference only |
keywords | yes | yes | Matching rules |

---

### `name`
Appears in CSV output column `Category`.

Example CSV row:
```
RE2026010224,22.01.2026,Customer A,Transport,340
```

---

### `label`
Optional field. Not used by the script.  
Can be used for documentation or UI display.

---

### `keywords`
List of match rules.  
Matching is **case‑insensitive**.

Supported formats:

#### 1) Text match (most common)
Matches if text contains substring.

```
- "transport"
```

Matches:
- Transport service
- Rücktransport
- TRANSPORT FEE

---

#### 2) Regex match
Regex must be wrapped in `/ /`.

Example:
```
- "/^ship(ping)?/"
```

Matches:
- ship
- shipping

If regex is invalid, script falls back to substring search.

---

## Matching logic (important)

Rules are evaluated **top → bottom**.

Meaning:

```
categories:
  - name: A
    keywords: ["service"]

  - name: B
    keywords: ["service fee"]
```

Text:
```
Service fee
```

Result → Category A  
because it matched first.

👉 Therefore:
**Always place more specific categories above generic ones**

---

## Real example explained

Your config:

```yaml
- name: Transport
  keywords:
    - "transport"
    - "lkw"
```

Line item:
```
LKW Transport München
```

→ matched because:
- contains "lkw"
- contains "transport"

---

## How script uses mapping internally

For each line item:

1. Normalize text → lowercase + trim spaces
2. Check category 1 keywords
3. If match → assign category → stop
4. If no match → check next category
5. If nothing matches → use `default_category`

---

## Best practices

Recommended ordering:

1. Specific categories
2. Medium specificity
3. Generic categories
4. Fallback category

Example good order:
```
Transport
Storage
Rental
Sales
Additional charges
```

---

## Testing mapping

Run CSV A with logging for unmapped lines:

```bash
python3 csv_a.py --month 2026-01 --log-unmapped
```

Log will show:
```
unmapped_lineitems invoiceNumber=... titles=[...]
```

Add missing keywords to mapping.yaml until all important items are categorized.

---

## Common mistakes

❌ Too generic keyword:
```
- "service"
```
This may capture unrelated items.

✔ Better:
```
- "service fee"
- "service charge"
```

---

❌ Wrong order

Generic rule before specific rule.

✔ Put specific rules first.

---

## Editing safely

After editing mapping.yaml:

1) Save file  
2) Run test export:
```
python3 csv_a.py --month 2026-01
```

3) Inspect CSV output

No restart or build step is needed.

---

## Summary

mapping.yaml controls how revenue is categorized.

You only need to edit this file when:
- a new revenue type appears
- categorization should change
- unmapped items appear in logs

No code changes required.
