# Product API Code Review — Case Study

## Problem Statement

The provided Flask API endpoint for product creation contains **7 issues** spanning input validation, data integrity, security, and API design — any of which could cause failures or data corruption in production.

---

## Issues Found

| # | Issue | Severity |
|---|-------|----------|
| 1 | No input validation — crashes on missing/malformed fields | Critical |
| 2 | Non-atomic transaction — two separate commits cause data corruption | Critical |
| 3 | No SKU uniqueness check — allows duplicate SKUs | Critical |
| 4 | No price validation — accepts negative, zero, or string values | High |
| 5 | `initial_quantity` unvalidated — KeyError or negative values stored | High |
| 6 | No authentication — endpoint publicly accessible | High |
| 7 | Returns HTTP 200 instead of 201 Created | Medium |

---

## Repository Structure

```
product-api-review/
│
├── README.md                        ← This file
├── original_code.py                 ← Original buggy code (annotated)
├── fixed_code.py                    ← Corrected implementation with comments
├── ANALYSIS.md                      ← Detailed breakdown of every issue
└── tests/
    └── test_create_product.py       ← Unit tests covering all 7 issues
```

---

## Key Fixes at a Glance

### Fix 1 — Safe Input Validation
```python
# Before
data = request.json
product = Product(name=data['name'], ...)  # KeyError if missing

# After
data = request.get_json(silent=True)
if not data:
    return jsonify({"error": "Request body must be valid JSON"}), 400
missing = [f for f in required_fields if f not in data or data[f] is None]
if missing:
    return jsonify({"error": f"Missing required fields: {', '.join(missing)}"}), 400
```

### Fix 2 — Atomic Transaction
```python
# Before
db.session.commit()  # saves product
db.session.commit()  # saves inventory — if this fails, product exists with no inventory

# After
db.session.flush()   # gets product.id without committing
db.session.add(inventory)
db.session.commit()  # single commit — both saved or neither is
```

### Fix 3 — SKU Uniqueness
```python
# Before
# No check — raw IntegrityError crashes as 500

# After
if Product.query.filter_by(sku=data['sku']).first():
    return jsonify({"error": "SKU already exists"}), 409
```

### Fix 4 — Price Validation
```python
# Before
price=data['price']  # could be -99, "free", or None

# After
price = Decimal(str(data['price'])).quantize(Decimal('0.01'))
if price <= 0:
    return jsonify({"error": "Price must be a positive decimal number"}), 400
```

### Fix 5 — Quantity Validation
```python
# Before
quantity=data['initial_quantity']  # KeyError if missing

# After
initial_quantity = data.get('initial_quantity', 0)  # defaults to 0
if not isinstance(initial_quantity, int) or initial_quantity < 0:
    return jsonify({"error": "initial_quantity must be a non-negative integer"}), 400
```

### Fix 6 — Authentication
```python
# Before
@app.route('/api/products', methods=['POST'])
def create_product():  # No auth — anyone can call this

# After
@app.route('/api/products', methods=['POST'])
@require_auth  # Returns 401 if token missing or invalid
def create_product():
```

### Fix 7 — Correct HTTP Status Code
```python
# Before
return {"message": "Product created", "product_id": product.id}  # 200 OK

# After
response = jsonify({...})
response.status_code = 201  # 201 Created
response.headers['Location'] = f"/api/products/{product.id}"
return response
```

---

## How to Run the Tests

```bash
# Install dependencies
pip install flask pytest

# Run all tests
pytest tests/test_create_product.py -v
```

---

## Beyond the Code — Production Considerations

| Concern | Recommendation |
|--------|----------------|
| Schema validation | Use `marshmallow` or `pydantic` for cleaner validation |
| Rate limiting | Add `flask-limiter` to prevent API abuse |
| Observability | Log all failures with a request ID for traceability |
| DB constraints | Add `UNIQUE` constraint on `sku` column as a safety net |
| API versioning | Use `/api/v1/products` to allow future breaking changes |

---

## Most Critical Issue

**Issue 2 (Non-atomic transaction)** is the most dangerous in production. It causes **silent data corruption** — a product can exist in the database permanently without any inventory record. This is hard to detect, affects customers directly, and is painful to fix manually at scale.

The fix — using `flush()` + a single `commit()` with a `rollback()` on failure — ensures both the product and inventory are always saved together or not at all.
# Aditya_Gaikwad_casestudy
