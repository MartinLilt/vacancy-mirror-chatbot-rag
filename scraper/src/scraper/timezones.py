"""Upwork timezone filter values.

These match the ``timezone`` query parameter accepted by Upwork's job search.
Each value corresponds to one of the 72 timezone options in Upwork's
"Client timezone" filter dropdown.

URL example:
    https://www.upwork.com/nx/search/jobs/?category2_uid=...
    &contractor_tier=1&timezone=America%2FNew_York
"""

UPWORK_TIMEZONES: list[str] = [
    # UTC-11
    "Pacific/Midway",
    # UTC-10
    "Pacific/Honolulu",
    # UTC-8
    "America/Nome",
    # UTC-7
    "America/Los_Angeles",
    "America/Tijuana",
    "America/Phoenix",
    # UTC-6
    "America/Denver",
    "America/Regina",
    "America/Indiana/Knox",
    "America/Managua",
    "America/Mexico_City",
    # UTC-5
    "America/Chicago",
    "America/Bogota",
    "America/Indiana/Indianapolis",
    # UTC-4
    "America/New_York",
    "America/Halifax",
    "America/La_Paz",
    "America/Caracas",
    # UTC-3
    "America/Fortaleza",
    "America/Buenos_Aires",
    "America/Recife",
    "America/Sao_Paulo",
    # UTC-2:30
    "America/St_Johns",
    # UTC-2
    "Atlantic/South_Georgia",
    # UTC-1 / UTC+0
    "Atlantic/Azores",
    "Africa/Casablanca",
    "Etc/UTC",
    # UTC+1
    "Europe/London",
    "Europe/Lisbon",
    "Africa/Algiers",
    # UTC+2
    "Europe/Prague",
    "Europe/Paris",
    "Europe/Berlin",
    "EET",
    "Africa/Cairo",
    "Africa/Harare",
    # UTC+3
    "Europe/Athens",
    "Asia/Jerusalem",
    "Europe/Minsk",
    "Europe/Moscow",
    "Asia/Baghdad",
    # UTC+3:30
    "Asia/Tehran",
    # UTC+4
    "Asia/Tbilisi",
    "Asia/Yerevan",
    # UTC+4:30
    "Asia/Kabul",
    # UTC+5
    "Asia/Karachi",
    "Asia/Tashkent",
    "Asia/Yekaterinburg",
    # UTC+5:30
    "Asia/Calcutta",
    # UTC+5:45
    "Asia/Katmandu",
    # UTC+6
    "Asia/Almaty",
    "Asia/Omsk",
    # UTC+7
    "Asia/Krasnoyarsk",
    "Asia/Bangkok",
    # UTC+8
    "Australia/Perth",
    "Asia/Irkutsk",
    "Asia/Shanghai",
    # UTC+9
    "Asia/Tokyo",
    "Asia/Yakutsk",
    # UTC+9:30
    "Australia/Darwin",
    "Australia/Adelaide",
    # UTC+10
    "Pacific/Guam",
    "Asia/Vladivostok",
    "Australia/Hobart",
    "Australia/Brisbane",
    "Australia/Sydney",
    # UTC+11
    "Asia/Magadan",
    # UTC+12
    "Pacific/Fiji",
    "Pacific/Auckland",
    "Pacific/Kwajalein",
    "Asia/Kamchatka",
    # UTC+13
    "Pacific/Apia",
]

