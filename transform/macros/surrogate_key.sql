{% macro surrogate_key(field_list) %}
    {#
        Thin wrapper around dbt_utils.generate_surrogate_key so every surrogate key
        in this project is built the same way, in one place to change. Not used by
        any staging model yet (staging keeps natural keys, not surrogate ones) --
        this exists here because AE-07 is where the project's macro conventions get
        established; AE-10 is the first real consumer, building dim_customer's
        surrogate key from (customer_id, valid_from).
    #}
    {{ dbt_utils.generate_surrogate_key(field_list) }}
{% endmacro %}
