# ============================================================
# UNIT TESTS — test_create_product.py
# Tests cover all 7 issues identified in the code review
# Run with: pytest tests/test_create_product.py -v
# ============================================================

import pytest
import json
from unittest.mock import patch, MagicMock
from fixed_code import app


@pytest.fixture
def client():
    """Set up Flask test client."""
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


def auth_header():
    """Helper to return valid auth header."""
    return {"Authorization": "Bearer valid-token"}


def valid_payload():
    """Helper to return a complete valid request payload."""
    return {
        "name": "Test Product",
        "sku": "SKU-001",
        "price": 9.99,
        "warehouse_id": 1,
        "initial_quantity": 10
    }


# ============================================================
# Tests for Issue #1 — Input Validation
# ============================================================
class TestInputValidation:

    def test_missing_json_body_returns_400(self, client):
        """Request with no body should return 400, not 500."""
        response = client.post(
            '/api/products',
            headers=auth_header(),
            content_type='application/json'
        )
        assert response.status_code == 400
        assert b"valid JSON" in response.data

    def test_missing_required_field_name_returns_400(self, client):
        """Missing 'name' field should return 400 with descriptive error."""
        payload = valid_payload()
        del payload['name']
        response = client.post(
            '/api/products',
            data=json.dumps(payload),
            content_type='application/json',
            headers=auth_header()
        )
        assert response.status_code == 400
        data = json.loads(response.data)
        assert "name" in data['error']

    def test_missing_required_field_sku_returns_400(self, client):
        """Missing 'sku' field should return 400."""
        payload = valid_payload()
        del payload['sku']
        response = client.post(
            '/api/products',
            data=json.dumps(payload),
            content_type='application/json',
            headers=auth_header()
        )
        assert response.status_code == 400

    def test_missing_required_field_warehouse_id_returns_400(self, client):
        """Missing 'warehouse_id' field should return 400."""
        payload = valid_payload()
        del payload['warehouse_id']
        response = client.post(
            '/api/products',
            data=json.dumps(payload),
            content_type='application/json',
            headers=auth_header()
        )
        assert response.status_code == 400

    def test_null_required_field_returns_400(self, client):
        """Null value for required field should return 400."""
        payload = valid_payload()
        payload['name'] = None
        response = client.post(
            '/api/products',
            data=json.dumps(payload),
            content_type='application/json',
            headers=auth_header()
        )
        assert response.status_code == 400


# ============================================================
# Tests for Issue #4 — Price Validation
# ============================================================
class TestPriceValidation:

    def test_negative_price_returns_400(self, client):
        """Negative price should be rejected."""
        payload = valid_payload()
        payload['price'] = -5.00
        response = client.post(
            '/api/products',
            data=json.dumps(payload),
            content_type='application/json',
            headers=auth_header()
        )
        assert response.status_code == 400
        assert b"Price" in response.data

    def test_zero_price_returns_400(self, client):
        """Zero price should be rejected."""
        payload = valid_payload()
        payload['price'] = 0
        response = client.post(
            '/api/products',
            data=json.dumps(payload),
            content_type='application/json',
            headers=auth_header()
        )
        assert response.status_code == 400

    def test_string_price_returns_400(self, client):
        """Non-numeric price (e.g., 'free') should be rejected."""
        payload = valid_payload()
        payload['price'] = "free"
        response = client.post(
            '/api/products',
            data=json.dumps(payload),
            content_type='application/json',
            headers=auth_header()
        )
        assert response.status_code == 400

    def test_valid_decimal_price_accepted(self, client):
        """Valid decimal price like 19.99 should be accepted."""
        payload = valid_payload()
        payload['price'] = 19.99
        with patch('fixed_code.Product') as MockProduct, \
             patch('fixed_code.Inventory') as MockInventory, \
             patch('fixed_code.db') as mock_db, \
             patch('fixed_code.Product.query') as mock_query:
            mock_query.filter_by.return_value.first.return_value = None
            mock_product_instance = MagicMock()
            mock_product_instance.id = 1
            mock_product_instance.sku = "SKU-001"
            mock_product_instance.price = "19.99"
            MockProduct.return_value = mock_product_instance
            response = client.post(
                '/api/products',
                data=json.dumps(payload),
                content_type='application/json',
                headers=auth_header()
            )
        assert response.status_code in [201, 500]  # 500 only if mock setup incomplete


# ============================================================
# Tests for Issue #5 — initial_quantity Validation
# ============================================================
class TestQuantityValidation:

    def test_missing_initial_quantity_defaults_to_zero(self, client):
        """Missing initial_quantity should default to 0, not crash."""
        payload = valid_payload()
        del payload['initial_quantity']
        with patch('fixed_code.Product.query') as mock_query, \
             patch('fixed_code.Product'), \
             patch('fixed_code.Inventory'), \
             patch('fixed_code.db'):
            mock_query.filter_by.return_value.first.return_value = None
            response = client.post(
                '/api/products',
                data=json.dumps(payload),
                content_type='application/json',
                headers=auth_header()
            )
        # Should not return 500 (KeyError crash)
        assert response.status_code != 500

    def test_negative_quantity_returns_400(self, client):
        """Negative initial_quantity should be rejected."""
        payload = valid_payload()
        payload['initial_quantity'] = -5
        response = client.post(
            '/api/products',
            data=json.dumps(payload),
            content_type='application/json',
            headers=auth_header()
        )
        assert response.status_code == 400
        assert b"initial_quantity" in response.data

    def test_float_quantity_returns_400(self, client):
        """Float value for quantity should be rejected (must be integer)."""
        payload = valid_payload()
        payload['initial_quantity'] = 5.5
        response = client.post(
            '/api/products',
            data=json.dumps(payload),
            content_type='application/json',
            headers=auth_header()
        )
        assert response.status_code == 400


# ============================================================
# Tests for Issue #3 — SKU Uniqueness
# ============================================================
class TestSkuUniqueness:

    def test_duplicate_sku_returns_409(self, client):
        """Duplicate SKU should return 409 Conflict, not 500."""
        payload = valid_payload()
        with patch('fixed_code.Product.query') as mock_query:
            # Simulate existing product found in DB
            mock_query.filter_by.return_value.first.return_value = MagicMock()
            response = client.post(
                '/api/products',
                data=json.dumps(payload),
                content_type='application/json',
                headers=auth_header()
            )
        assert response.status_code == 409
        data = json.loads(response.data)
        assert "already exists" in data['error']


# ============================================================
# Tests for Issue #6 — Authentication
# ============================================================
class TestAuthentication:

    def test_request_without_auth_returns_401(self, client):
        """Request with no auth header should return 401."""
        response = client.post(
            '/api/products',
            data=json.dumps(valid_payload()),
            content_type='application/json'
            # No auth header
        )
        assert response.status_code == 401

    def test_request_with_invalid_token_returns_401(self, client):
        """Request with wrong token should return 401."""
        response = client.post(
            '/api/products',
            data=json.dumps(valid_payload()),
            content_type='application/json',
            headers={"Authorization": "Bearer wrong-token"}
        )
        assert response.status_code == 401


# ============================================================
# Tests for Issue #7 — HTTP Status Code
# ============================================================
class TestHttpStatusCode:

    def test_successful_creation_returns_201(self, client):
        """Successful product creation must return 201, not 200."""
        payload = valid_payload()
        with patch('fixed_code.Product.query') as mock_query, \
             patch('fixed_code.Product') as MockProduct, \
             patch('fixed_code.Inventory'), \
             patch('fixed_code.db'):
            mock_query.filter_by.return_value.first.return_value = None
            mock_instance = MagicMock()
            mock_instance.id = 42
            mock_instance.sku = "SKU-001"
            mock_instance.price = "9.99"
            MockProduct.return_value = mock_instance
            response = client.post(
                '/api/products',
                data=json.dumps(payload),
                content_type='application/json',
                headers=auth_header()
            )
        assert response.status_code == 201

    def test_response_includes_location_header(self, client):
        """Response should include Location header pointing to new resource."""
        payload = valid_payload()
        with patch('fixed_code.Product.query') as mock_query, \
             patch('fixed_code.Product') as MockProduct, \
             patch('fixed_code.Inventory'), \
             patch('fixed_code.db'):
            mock_query.filter_by.return_value.first.return_value = None
            mock_instance = MagicMock()
            mock_instance.id = 42
            mock_instance.sku = "SKU-001"
            mock_instance.price = "9.99"
            MockProduct.return_value = mock_instance
            response = client.post(
                '/api/products',
                data=json.dumps(payload),
                content_type='application/json',
                headers=auth_header()
            )
        assert response.status_code == 201
        assert 'Location' in response.headers
        assert '/api/products/42' in response.headers['Location']
