{% macro cents_to_decimal(column) %}
    {#
        Normalizes the cents-vs-decimal money defect (AE-02): `payments`/`refunds`
        store integer cents, while `orders`/`product_prices` store decimal dollars.
        One macro, one place to change if the unit convention ever changes --
        every money column that needs this conversion calls the same definition.
    #}
    (CAST({{ column }} AS DECIMAL(18, 2)) / 100.0)
{% endmacro %}
