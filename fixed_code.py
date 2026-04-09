# ============================================================
# FIXED CODE — Corrected implementation with all issues resolved
# 
# Issues fixed:
#   1. [CRITICAL] Input validation added
#   2. [CRITICAL] Atomic transaction using flush() + single commit()
#   3. [CRITICAL] SKU uniqueness check added
#   4. [HIGH]     Price validated as positive Decimal
#   5. [HIGH]     initial_quantity optional with safe default
#   6. [HIGH]     Authentication decorator added
#   7. [MEDIUM]   Returns 201 Created with Location header
# ============================================================

from flask import Flask, request, jsonify
from sqlalchemy.exc import IntegrityError
from decimal import Decimal, InvalidOperation
from functools import wraps

app = Flask(__name__)


# ============================================================
# FIX #6 — AUTHENTICATION DECORATOR
#
# ORIGINAL PROBLEM:
#   The original endpoint had zero access control.
#   Any anonymous HTTP request from anywhere on the internet
#   could call POST /api/products and insert rows into your DB.
#
# WHY IT MATTERS IN PRODUCTION:
#   - Competitors or bots can flood your catalog with fake products
#   - No audit trail of who created what
#   - A basic security requirement that was completely missing
#
# HOW THE FIX WORKS:
#   This decorator wraps any route function and checks for a
#   valid Authorization header BEFORE the route logic runs.
#   If the token is missing or invalid, it immediately returns
#   401 Unauthorized and never enters the route function.
#
#   Replace is_valid_token() with your actual auth logic —
#   JWT verification, session lookup, API key check, etc.
# ============================================================
def require_auth(f):
    @wraps(f)  # preserves the original function's name and docstring
    def decorated(*args, **kwargs):
        token = request.headers.get("Authorization")

        # If no token provided at all, reject immediately
        if not token:
            return jsonify({"error": "Authorization header is missing"}), 401

        # If token is invalid, reject with 401
        if not is_valid_token(token):
            return jsonify({"error": "Invalid or expired token"}), 401

        # Token is valid — proceed to the actual route handler
        return f(*args, **kwargs)
    return decorated


def is_valid_token(token):
    """
    Validates the authorization token.
    Replace this with your real auth logic:
      - JWT: decode and verify signature + expiry
      - API Key: lookup token in DB/cache
      - Session: verify session ID is active
    """
    return token == "Bearer valid-token"  # placeholder — replace in production


# ============================================================
# MAIN ENDPOINT — CREATE PRODUCT
# ============================================================
@app.route('/api/products', methods=['POST'])
@require_auth  # FIX #6: Auth check runs before anything else
def create_product():
    """
    Creates a new product and its initial inventory record.
    Both are saved atomically — either both succeed or neither does.

    Request Body (JSON):
        name            (str, required)  — Product display name
        sku             (str, required)  — Unique product identifier
        price           (decimal, required) — Must be positive
        warehouse_id    (int, required)  — Warehouse to stock product in
        initial_quantity (int, optional) — Starting inventory count, defaults to 0

    Returns:
        201 Created     — Product and inventory created successfully
        400 Bad Request — Missing fields, invalid price, or invalid quantity
        401 Unauthorized — Missing or invalid auth token
        409 Conflict    — A product with this SKU already exists
        500 Server Error — Unexpected DB or server failure
    """

    # ----------------------------------------------------------
    # FIX #1 — SAFE JSON PARSING
    #
    # ORIGINAL CODE:
    #   data = request.json
    #
    # PROBLEM:
    #   request.json raises a 400 error silently OR returns None
    #   if the Content-Type header is not 'application/json'.
    #   Any subsequent data['field'] access on None crashes with
    #   TypeError → unhandled 500 Internal Server Error.
    #
    # FIX:
    #   request.get_json(silent=True) safely returns None instead
    #   of raising an exception when parsing fails. We then check
    #   for None explicitly and return a clean 400 with a message
    #   the API caller can actually understand and act on.
    # ----------------------------------------------------------
    data = request.get_json(silent=True)

    if not data:
        return jsonify({
            "error": "Request body must be valid JSON",
            "hint": "Ensure Content-Type header is set to application/json"
        }), 400


    # ----------------------------------------------------------
    # FIX #1 (continued) — REQUIRED FIELD VALIDATION
    #
    # ORIGINAL CODE:
    #   product = Product(name=data['name'], sku=data['sku'], ...)
    #
    # PROBLEM:
    #   Directly accessing data['field'] raises KeyError if the
    #   field is absent — which Flask turns into a 500 error.
    #   The caller gets no useful information about what went wrong.
    #
    # FIX:
    #   Explicitly define which fields are required, check all of
    #   them upfront before touching the database, and return a
    #   single 400 response listing ALL missing fields at once.
    #   This is far better UX than failing one field at a time.
    # ----------------------------------------------------------
    required_fields = ['name', 'sku', 'price', 'warehouse_id']
    missing = [
        field for field in required_fields
        if field not in data or data[field] is None
    ]

    if missing:
        return jsonify({
            "error": f"Missing required fields: {', '.join(missing)}"
        }), 400

    # Validate name is not just whitespace
    if not str(data['name']).strip():
        return jsonify({"error": "Product name cannot be blank"}), 400

    # Validate SKU is not just whitespace
    if not str(data['sku']).strip():
        return jsonify({"error": "SKU cannot be blank"}), 400


    # ----------------------------------------------------------
    # FIX #4 — PRICE VALIDATION
    #
    # ORIGINAL CODE:
    #   price=data['price']  # stored as-is, no checks
    #
    # PROBLEM 1 — Wrong type:
    #   Price could be a string ("free"), None, or a boolean (True).
    #   Storing "free" as a price will break any billing system.
    #
    # PROBLEM 2 — Negative or zero values:
    #   price=-99 or price=0 would be stored silently.
    #   Negative prices break billing; zero prices bypass payment.
    #
    # PROBLEM 3 — Float precision:
    #   Python floats have precision issues: 0.1 + 0.2 = 0.30000000000000004
    #   For financial values, always use Decimal, not float.
    #
    # FIX:
    #   Convert to Decimal (safe for money), quantize to 2dp,
    #   and enforce price > 0. InvalidOperation is raised by
    #   Decimal() if the input is not a valid number at all.
    # ----------------------------------------------------------
    try:
        # Convert via str() first to safely handle int/float/string inputs
        price = Decimal(str(data['price'])).quantize(Decimal('0.01'))

        if price <= 0:
            # Explicit check — zero and negative prices are invalid
            raise ValueError("Price must be greater than zero")

    except InvalidOperation:
        # Raised when input cannot be parsed as a number (e.g., "free", "abc")
        return jsonify({
            "error": "Price must be a valid number (e.g. 9.99)"
        }), 400

    except ValueError as e:
        # Raised by our own check above for zero/negative values
        return jsonify({"error": str(e)}), 400


    # ----------------------------------------------------------
    # FIX #5 — initial_quantity VALIDATION
    #
    # ORIGINAL CODE:
    #   quantity=data['initial_quantity']  # direct access, no default
    #
    # PROBLEM 1 — Missing field:
    #   Per the context, some fields are optional. If the caller
    #   doesn't send initial_quantity, this crashes with KeyError → 500.
    #
    # PROBLEM 2 — Negative values:
    #   quantity=-10 would be stored silently, corrupting all
    #   inventory reports and stock calculations.
    #
    # PROBLEM 3 — Wrong type:
    #   quantity=5.5 (float) or quantity="ten" (string) would fail
    #   at the DB level with a confusing error, not a clean 400.
    #
    # FIX:
    #   Use data.get() with a default of 0 (optional field).
    #   Validate it is a non-negative integer before proceeding.
    # ----------------------------------------------------------
    initial_quantity = data.get('initial_quantity', 0)  # defaults to 0 if not provided

    if not isinstance(initial_quantity, int) or isinstance(initial_quantity, bool):
        # isinstance check: bool is a subclass of int in Python,
        # so True/False would pass an int check — exclude explicitly
        return jsonify({
            "error": "initial_quantity must be an integer"
        }), 400

    if initial_quantity < 0:
        return jsonify({
            "error": "initial_quantity cannot be negative"
        }), 400


    # ----------------------------------------------------------
    # FIX #3 — SKU UNIQUENESS CHECK
    #
    # ORIGINAL CODE:
    #   (No check at all — just inserted directly)
    #
    # PROBLEM:
    #   If a product with the same SKU already exists and a UNIQUE
    #   constraint is set on the DB column, the commit raises an
    #   IntegrityError — which becomes an unhandled 500.
    #   If there's no DB constraint, silent duplicates are created.
    #
    # FIX (two-layer defense):
    #
    #   Layer 1 (here): Query before inserting. Returns a clean
    #   409 Conflict with a human-readable message. Fast and clear.
    #
    #   Layer 2 (in except block below): Even if two simultaneous
    #   requests both pass this check at the same millisecond
    #   (race condition), the DB IntegrityError is caught and
    #   returns the same clean 409 instead of crashing as 500.
    #
    # NOTE: SKU is normalized to uppercase before all checks so
    #   "sku-001", "SKU-001", and "Sku-001" are treated the same.
    # ----------------------------------------------------------
    normalized_sku = data['sku'].strip().upper()

    existing_product = Product.query.filter_by(sku=normalized_sku).first()
    if existing_product:
        return jsonify({
            "error": f"A product with SKU '{normalized_sku}' already exists",
            "existing_product_id": existing_product.id
        }), 409  # 409 Conflict is the correct HTTP code for duplicate resource


    # ----------------------------------------------------------
    # FIX #2 — ATOMIC TRANSACTION (single commit)
    #
    # ORIGINAL CODE:
    #   db.session.add(product)
    #   db.session.commit()       ← Commit 1: Product saved permanently
    #   ...
    #   db.session.add(inventory)
    #   db.session.commit()       ← Commit 2: If this fails, product exists without inventory
    #
    # PROBLEM:
    #   Two separate commits mean these are two separate DB transactions.
    #   If ANYTHING fails between commit 1 and commit 2 — a DB hiccup,
    #   a server restart, a constraint violation on inventory — the product
    #   row is permanently saved with NO inventory record.
    #   This is silent data corruption. A product exists in your catalog
    #   that has no stock entry. Very hard to detect, painful to fix at scale.
    #
    # FIX:
    #   Step 1: db.session.add(product) — stages the product object
    #   Step 2: db.session.flush() — sends the INSERT to the DB within
    #           the current transaction (so product.id is generated and
    #           available) but does NOT commit. The row is not permanently
    #           saved yet — it's in a pending state.
    #   Step 3: db.session.add(inventory) — stages inventory using product.id
    #   Step 4: db.session.commit() — ONE commit saves BOTH records together.
    #           If this fails for any reason, NEITHER is saved.
    #
    #   The try/except ensures that any failure triggers a rollback(),
    #   which discards ALL pending changes from this transaction cleanly.
    # ----------------------------------------------------------
    try:
        # --- Create the Product object ---
        product = Product(
            name=data['name'].strip(),       # strip() removes accidental leading/trailing spaces
            sku=normalized_sku,              # use the normalized (uppercase, stripped) SKU
            price=price,                     # Decimal value, safe for financial storage
            warehouse_id=data['warehouse_id']
        )
        db.session.add(product)

        # flush() assigns product.id from the DB sequence/autoincrement
        # WITHOUT committing the transaction — product is NOT saved yet
        db.session.flush()

        # --- Create the Inventory record using the flushed product.id ---
        inventory = Inventory(
            product_id=product.id,           # now available thanks to flush()
            warehouse_id=data['warehouse_id'],
            quantity=initial_quantity
        )
        db.session.add(inventory)

        # --- SINGLE COMMIT — saves both Product and Inventory atomically ---
        # Either both are saved, or neither is. No orphaned records possible.
        db.session.commit()

    except IntegrityError:
        # ----------------------------------------------------------
        # Handles race condition for duplicate SKU:
        # Two requests with the same SKU could both pass the query
        # check above at the same time. The second one to commit will
        # hit a UNIQUE constraint violation here. We catch it cleanly.
        # Also catches other DB constraint violations (FK, NOT NULL, etc.)
        # ----------------------------------------------------------
        db.session.rollback()  # discard ALL pending changes from this transaction
        return jsonify({
            "error": "A product with this SKU already exists (conflict detected at DB level)"
        }), 409

    except Exception as e:
        # ----------------------------------------------------------
        # Catches any other unexpected failure:
        # DB connection lost, disk full, timeout, unexpected data issue, etc.
        # Always rollback to ensure DB is in a clean state.
        # Log the error server-side (never expose raw error to client).
        # ----------------------------------------------------------
        db.session.rollback()  # critical: always rollback on any failure
        app.logger.error(f"Unexpected error creating product: {e}", exc_info=True)
        return jsonify({
            "error": "An internal server error occurred. Please try again."
        }), 500


    # ----------------------------------------------------------
    # FIX #7 — RETURN 201 CREATED (not 200 OK)
    #
    # ORIGINAL CODE:
    #   return {"message": "Product created", "product_id": product.id}
    #   # Flask defaults this to HTTP 200 OK
    #
    # PROBLEM:
    #   HTTP 200 OK means "request succeeded, here's the response."
    #   HTTP 201 Created is the correct code for successful resource creation.
    #   Many API clients, monitoring tools, and test suites check for 201
    #   specifically to confirm a resource was created.
    #
    #   Also missing: the Location header, which REST convention says
    #   should point to the URL of the newly created resource.
    #   Without it, callers must construct the URL themselves.
    #
    # FIX:
    #   Explicitly set status_code = 201 on the response object.
    #   Add Location header pointing to /api/products/{id}.
    #   Include sku and price in response so callers don't need
    #   an extra GET request to confirm what was saved.
    # ----------------------------------------------------------
    response = jsonify({
        "message": "Product created successfully",
        "product_id": product.id,
        "sku": product.sku,           # confirm the normalized SKU that was saved
        "price": str(product.price),  # str() to serialize Decimal cleanly as "9.99"
        "warehouse_id": data['warehouse_id'],
        "initial_quantity": initial_quantity
    })
    response.status_code = 201  # 201 Created — correct for resource creation
    response.headers['Location'] = f"/api/products/{product.id}"  # REST convention
    return response


# ============================================================
# SUMMARY OF ALL FIXES
#
#  Issue | Description                          | Fix Applied
# -------+--------------------------------------+---------------------------
#    1   | No input validation                  | get_json(silent=True) +
#        |                                      | required field checks
# -------+--------------------------------------+---------------------------
#    2   | Two commits (non-atomic)             | flush() + single commit()
#        |                                      | + rollback() on failure
# -------+--------------------------------------+---------------------------
#    3   | No SKU uniqueness check              | Query before insert +
#        |                                      | catch IntegrityError → 409
# -------+--------------------------------------+---------------------------
#    4   | No price validation                  | Decimal parsing +
#        |                                      | positive value check
# -------+--------------------------------------+---------------------------
#    5   | initial_quantity unvalidated         | data.get() with default 0
#        |                                      | + non-negative int check
# -------+--------------------------------------+---------------------------
#    6   | No authentication                    | @require_auth decorator
#        |                                      | returning 401 on failure
# -------+--------------------------------------+---------------------------
#    7   | Wrong HTTP status code (200 vs 201)  | status_code = 201 +
#        |                                      | Location header added
# ============================================================
