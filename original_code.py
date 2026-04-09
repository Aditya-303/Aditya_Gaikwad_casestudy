# ============================================================
# ORIGINAL CODE — PROVIDED BY INTERN (BUGGY)
# Do NOT use in production. See fixed_code.py for corrections.
# ============================================================

@app.route('/api/products', methods=['POST'])
def create_product():
    data = request.json

    # Create new product
    product = Product(
        name=data['name'],
        sku=data['sku'],
        price=data['price'],
        warehouse_id=data['warehouse_id']
    )

    db.session.add(product)
    db.session.commit()  # BUG: First commit — if second fails, product exists without inventory

    # Update inventory count
    inventory = Inventory(
        product_id=product.id,
        warehouse_id=data['warehouse_id'],
        quantity=data['initial_quantity']  # BUG: KeyError if field missing
    )

    db.session.add(inventory)
    db.session.commit()  # BUG: Second separate commit — not atomic

    return {"message": "Product created", "product_id": product.id}  # BUG: Returns 200, should be 201


# ============================================================
# ISSUES IDENTIFIED:
#
# 1. [CRITICAL] No input validation — crashes on missing/malformed fields
# 2. [CRITICAL] Two separate commits — non-atomic, causes data corruption
# 3. [CRITICAL] No SKU uniqueness check — allows duplicate SKUs
# 4. [HIGH]     No price validation — accepts negative/zero/string prices
# 5. [HIGH]     initial_quantity unvalidated — KeyError or negative values
# 6. [HIGH]     No authentication — endpoint is publicly accessible
# 7. [MEDIUM]   Returns HTTP 200 instead of 201 Created
#
# See ANALYSIS.md for detailed explanation of each issue.
# See fixed_code.py for the corrected implementation.
# ============================================================
