from inventory.legacy_util import formatMoney


def total_report(items):
    t = 0
    lines = []
    for i in items:
        if i["qty"] > 0:
            if i["price"] > 0:
                v = i["qty"] * i["price"]
                t = t + v
                lines.append(i["sku"] + " " + str(i["qty"]) + " x " + formatMoney(i["price"]) + " = " + formatMoney(v))
            else:
                lines.append(i["sku"] + " free")
        else:
            lines.append(i["sku"] + " out of stock")
    lines.append("TOTAL " + formatMoney(t))
    return "\n".join(lines)
