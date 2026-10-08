"""ISO 4217 currencies the app accepts, with their number of minor-unit digits (the 'exponent').

All amounts are stored as integers in minor units; the exponent only matters when a person reads or types an amount:
1000 minor units are 10.00 USD but 1000 JPY and 1.000 KWD.
"""

_EXP0 = "BIF CLP DJF GNF ISK JPY KMF KRW PYG RWF UGX UYI VND VUV XAF XOF XPF"
_EXP3 = "BHD IQD JOD KWD LYD OMR TND"
_EXP2 = (
    "AED AFN ALL AMD ANG AOA ARS AUD AWG AZN BAM BBD BDT BGN BMD BND BOB BRL BSD BTN BWP BYN BZD CAD CDF CHF CNY COP CRC "
    "CUP CVE CZK DKK DOP DZD EGP ERN ETB EUR FJD FKP GBP GEL GHS GIP GMD GTQ GYD HKD HNL HTG HUF IDR ILS INR IRR JMD KES "
    "KGS KHR KYD KZT LAK LBP LKR LRD LSL MAD MDL MGA MKD MMK MNT MOP MRU MUR MVR MWK MXN MYR MZN NAD NGN NIO NOK NPR NZD "
    "PAB PEN PGK PHP PKR PLN QAR RON RSD RUB SAR SBD SCR SDG SEK SGD SHP SLE SOS SRD SSP STN SVC SYP SZL THB TJS TMT TOP "
    "TRY TTD TWD TZS UAH USD UYU UZS VES WST XCD YER ZAR ZMW ZWL"
)

CURRENCIES: dict[str, int] = {
    **{c: 0 for c in _EXP0.split()},
    **{c: 3 for c in _EXP3.split()},
    **{c: 2 for c in _EXP2.split()},
}


def exponent(code: str) -> int:
    return CURRENCIES.get(code.upper(), 2)


def format_minor(amount: int, code: str) -> str:
    exp = exponent(code)
    sign = "-" if amount < 0 else ""
    a = abs(amount)
    if exp == 0:
        return f"{sign}{a} {code}"
    return f"{sign}{a // 10**exp}.{a % 10**exp:0{exp}d} {code}"


def typescript_table() -> str:
    """The same table for the frontend (frontend/src/currencies.ts); a test keeps the two in sync."""
    rows = ",\n".join(f'  {c}: {e}' for c, e in sorted(CURRENCIES.items()) if e != 2)
    return (
        "// GENERATED from backend/app/currency.py by backend/scripts/gen_currencies.py. Do not edit.\n"
        "// Currencies not listed here have 2 minor-unit digits. A backend test fails if this file is out of date.\n"
        "export const CURRENCY_EXPONENTS: Record<string, number> = {\n" + rows + ",\n};\n"
        "export const KNOWN_CURRENCIES: string[] = " + repr(sorted(CURRENCIES)).replace("'", '"') + ";\n"
    )
