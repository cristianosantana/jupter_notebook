from smartchat.message_processing.cell_format import format_table_cell, parse_locale_number_string


def test_parse_locale_br_thousands_decimal():
    assert parse_locale_number_string("1.234,56") == 1234.56
    assert parse_locale_number_string("199.550") == 199550.0


def test_format_integer_grouping():
    assert format_table_cell(199550) == "199.550"
