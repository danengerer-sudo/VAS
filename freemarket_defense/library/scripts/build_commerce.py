"""Build category `commerce` -> build/commerce.blend, thumbs/commerce/*, catalog/commerce.json.

blender -b --factory-startup -P scripts/build_commerce.py [-- --only=a,b --nothumb]
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import commerce_lib as C  # noqa: E402
from genkit import MB, Category  # noqa: E402

cat = Category("commerce")


def add(name, body, tags, notes, bevel=0.0, az=-35, el=22, fill=1.0):
    def _():
        mb = MB()
        body(mb)
        return mb.build(name, bevel=bevel, merge=2e-6)
    cat.add(name, _, tags=tags, notes=notes, az=az, el=el, fill=fill)


# --- money
add("coin", lambda mb: C.coin(mb), ["coin", "money", "metal"], "Real-size 26.5 mm coin with $ relief. commerce_lib.coin(mb, d, t, symbol)",
    bevel=0.0002, el=40)
add("coin_stack", lambda mb: C.coin_stack(mb, 14), ["coin", "stack", "money", "savings"],
    "commerce_lib.coin_stack(mb, n=14)", bevel=0.0002)
add("coin_stacks_row", lambda mb: C.coin_stacks(mb), ["coin", "stacks", "growth", "savings"],
    "Row of stacks of different heights. commerce_lib.coin_stacks(mb, stacks=(14,9,18,6,11))", bevel=0.0002)
add("coin_pile", lambda mb: C.coin_pile(mb, 150), ["coin", "pile", "treasure", "money"],
    "Scattered mound of coins. commerce_lib.coin_pile(mb, n=150, radius=0.12, height=0.05, seed)", bevel=0.0, el=35)
add("banknote", lambda mb: C.banknote(mb), ["banknote", "cash", "money"], "Single curled note. commerce_lib.banknote(mb)",
    el=40)
add("banknote_bundle", lambda mb: C.banknote_bundle(mb), ["banknote", "bundle", "cash"],
    "Bundle of 100 notes with accent band. commerce_lib.banknote_bundle(mb, value='100')", bevel=0.0004, el=35)
add("cash_stack", lambda mb: C.cash_stack(mb), ["cash", "stack", "money"], "Brick of bundles. commerce_lib.cash_stack(mb, cols, rows, layers)",
    bevel=0.0004, el=30)
add("cash_pallet", lambda mb: C.cash_pallet(mb), ["cash", "pallet", "money", "wealth"],
    "EUR pallet stacked with cash blocks. commerce_lib.cash_pallet(mb, layers=8)", bevel=0.002)
add("briefcase_cash", lambda mb: C.briefcase_cash(mb), ["cash", "briefcase", "bribe", "money"],
    "Open briefcase full of bundles. commerce_lib.briefcase_cash(mb, open_deg=100)", bevel=0.001, el=35)
add("gold_bar", lambda mb: C.gold_bar(mb), ["gold", "bar", "bullion"], "400 oz bar, '999.9' stamp. commerce_lib.gold_bar(mb)",
    bevel=0.0008, el=30)
add("gold_pyramid", lambda mb: C.gold_pyramid(mb, 5), ["gold", "bullion", "reserve"], "Stepped pyramid of bars. commerce_lib.gold_pyramid(mb, base=5)",
    bevel=0.0008, el=25)
add("gold_pallet", lambda mb: C.gold_pallet(mb), ["gold", "bullion", "pallet", "reserve"], "Pallet of gold bars. commerce_lib.gold_pallet(mb, layers=6)",
    bevel=0.0008)
# --- bank fixtures
add("vault_door", lambda mb: C.vault_door(mb), ["vault", "bank", "security"], "Round vault door, closed. commerce_lib.vault_door(mb, r=1.2, open_deg=0)",
    bevel=0.01, az=-25)
add("vault_door_open", lambda mb: C.vault_door(mb, open_deg=70), ["vault", "bank", "security"],
    "Vault door swung open with bolts out. commerce_lib.vault_door(mb, open_deg=70)", bevel=0.01, az=-25)
add("safe", lambda mb: C.safe(mb), ["safe", "bank", "security"], "Floor safe with dial + handle. commerce_lib.safe(mb)",
    bevel=0.004)
add("atm", lambda mb: C.atm(mb), ["atm", "bank", "cash machine"], "Freestanding ATM, accent header. commerce_lib.atm(mb)",
    bevel=0.004)
add("cash_register", lambda mb: C.cash_register(mb), ["register", "pos", "shop", "retail"],
    "POS terminal with drawer, screen, printer, card reader. commerce_lib.cash_register(mb)", bevel=0.002)
add("shop_counter", lambda mb: C.shop_counter(mb), ["counter", "shop", "retail"], "Counter with display + register. commerce_lib.shop_counter(mb, length=2.4)",
    bevel=0.005)
add("market_stall", lambda mb: C.market_stall(mb), ["market", "stall", "trade", "produce"],
    "Striped canopy market stall with crates of produce. commerce_lib.market_stall(mb, w=3, d=1.6, seed)", bevel=0.005)
add("chalkboard_sign", lambda mb: C.chalkboard_sign(mb), ["sign", "price", "shop", "sale"],
    "A-frame chalkboard. commerce_lib.chalkboard_sign(mb, text1, text2)", bevel=0.003)
add("price_tag", lambda mb: C.price_tag(mb), ["price", "tag", "icon"], "Display-size swing tag. commerce_lib.price_tag(mb, text)",
    bevel=0.002, az=-20)
add("shopping_cart", lambda mb: C.shopping_cart(mb), ["shopping cart", "retail", "consumer"],
    "Wire trolley, accent handle. commerce_lib.shopping_cart(mb)", bevel=0.0)
add("shopping_bags", lambda mb: C.shopping_bags(mb), ["shopping bag", "retail", "consumer"],
    "Three paper bags. commerce_lib.shopping_bag(mb, w,d,h, m, logo)", bevel=0.002)
add("cardboard_box", lambda mb: C.cardboard_box(mb), ["box", "carton", "shipping", "logistics"],
    "Taped carton with label. commerce_lib.cardboard_box(mb, size, open_=False)", bevel=0.003)
add("cardboard_box_open", lambda mb: C.cardboard_box(mb, (0.45, 0.35, 0.3), open_=True), ["box", "carton", "open"],
    "Open carton. commerce_lib.cardboard_box(mb, open_=True)", bevel=0.0015)
add("box_pile", lambda mb: C.box_pile(mb), ["box", "carton", "pile", "logistics"], "Heap of cartons. commerce_lib.box_pile(mb)",
    bevel=0.003)
add("pallet", lambda mb: C.pallet(mb), ["pallet", "logistics"], "EUR pallet 1200x800x144. commerce_lib.pallet(mb)",
    bevel=0.003)
add("pallet_stack", lambda mb: C.pallet_stack(mb), ["pallet", "stack", "logistics"], "commerce_lib.pallet_stack(mb, n=6)",
    bevel=0.003)
add("pallet_boxes", lambda mb: C.pallet_boxes(mb), ["pallet", "boxes", "shipment", "trade"],
    "Loaded pallet. commerce_lib.pallet_boxes(mb, layers=3)", bevel=0.003)
add("warehouse_shelving", lambda mb: C.shelving(mb), ["shelving", "racking", "warehouse", "inventory"],
    "Pallet racking with accent beams + cartons. commerce_lib.shelving(mb, bays, levels, seed)", bevel=0.004)
# --- justice / office
add("scales_of_justice", lambda mb: C.scales_of_justice(mb, 0.18), ["justice", "law", "scales", "balance"],
    "Balance scales, tilt param (rad). commerce_lib.scales_of_justice(mb, tilt=0.18)", bevel=0.0, az=-60)
add("gavel", lambda mb: C.gavel(mb), ["gavel", "law", "court", "auction"], "Gavel on sound block. commerce_lib.gavel(mb)",
    bevel=0.001, el=30)
add("contract", lambda mb: C.contract(mb), ["contract", "document", "paper", "law"],
    "A4 contract with text lines, signature, accent seal. commerce_lib.contract(mb, title, signed)", el=55)
add("document_stack", lambda mb: C.document_stack(mb), ["documents", "paperwork", "bureaucracy", "regulation"],
    "Stack of papers + invoice + pen. commerce_lib.document_stack(mb, n=12)", el=40)
add("credit_card", lambda mb: C.credit_card(mb), ["credit card", "payment", "bank"],
    "ISO card, accent body, chip. commerce_lib.credit_card(mb, m)", el=45)
add("credit_cards_fan", lambda mb: C.credit_cards_fan(mb), ["credit card", "payment"], "Three fanned cards. commerce_lib.credit_cards_fan(mb)",
    el=45)
add("smartphone", lambda mb: C.smartphone(mb, standing=True), ["smartphone", "phone", "mobile", "tech"],
    "Phone on a stand, blank glass screen toward +X. commerce_lib.smartphone(mb, standing=True)", bevel=0.0005, az=-20)
add("laptop", lambda mb: C.laptop(mb), ["laptop", "computer", "office", "tech"], "Open laptop, screen faces +X. commerce_lib.laptop(mb, open_deg=110)",
    bevel=0.001, az=-30, el=25)
add("desk", lambda mb: C.desk(mb), ["desk", "office", "furniture"], "Office desk with drawer pedestal. commerce_lib.desk(mb)",
    bevel=0.004)
add("office_chair", lambda mb: C.office_chair(mb), ["chair", "office", "furniture"], "Swivel chair. commerce_lib.office_chair(mb)",
    bevel=0.004)
add("office_desk_set", lambda mb: C.office_desk_set(mb), ["desk", "office", "workplace"],
    "Desk + chair + laptop + phone + papers. commerce_lib.office_desk_set(mb)", bevel=0.003, az=-150)
add("lectern", lambda mb: C.lectern(mb, "PRESS"), ["podium", "lectern", "speech", "politics"],
    "Podium with accent front panel + mic. commerce_lib.lectern(mb, text)", bevel=0.004)
add("flag_on_pole", lambda mb: C.flag_on_pole(mb), ["flag", "nation", "faction"], "Waving accent flag with emblem. commerce_lib.flag_on_pole(mb, h=6, fw, fh)",
    bevel=0.0, az=-60)
add("flag_row", lambda mb: C.flag_row(mb), ["flag", "nation", "diplomacy"], "Three flags in a row. commerce_lib.flag_row(mb, n=3)",
    bevel=0.0, az=-60)
add("flag_indoor", lambda mb: C.flag_indoor(mb), ["flag", "office", "press room"], "Indoor stand flag. commerce_lib.flag_indoor(mb)",
    bevel=0.0, az=-60)
# --- data / icons
add("bar_chart", lambda mb: C.bar_chart(mb), ["chart", "bar chart", "data", "economy"],
    "3D bar chart; values, scale, highlight index. commerce_lib.bar_chart(mb, values=(3,5,4,7,9))", bevel=0.01, az=-20)
add("bar_chart_highlight", lambda mb: C.bar_chart(mb, (6, 4, 3, 2.5, 2), highlight=0), ["chart", "bar chart", "data"],
    "One accent bar, rest white. commerce_lib.bar_chart(mb, values, highlight=0)", bevel=0.01, az=-20)
add("line_chart", lambda mb: C.line_chart(mb), ["chart", "line chart", "growth", "data"],
    "Ribbon line chart with markers + arrow. commerce_lib.line_chart(mb, values=...)", bevel=0.0, az=-20)
add("pie_chart", lambda mb: C.pie_chart(mb), ["chart", "pie chart", "share", "data"],
    "Pie slices, first exploded with % label. commerce_lib.pie_chart(mb, values=(45,25,18,12))", bevel=0.01, el=40)
add("icon_dollar", lambda mb: C.currency_icon(mb, "$"), ["icon", "dollar", "currency", "money"],
    "1 m Inter-Black $ on a base. commerce_lib.currency_icon(mb, symbol, size, m)", bevel=0.005, az=-20)
add("icon_euro", lambda mb: C.currency_icon(mb, "€"), ["icon", "euro", "currency"], "commerce_lib.currency_icon(mb, '€')",
    bevel=0.005, az=-20)
add("icon_pound", lambda mb: C.currency_icon(mb, "£"), ["icon", "pound", "currency"], "commerce_lib.currency_icon(mb, '£')",
    bevel=0.005, az=-20)
add("icon_bitcoin", lambda mb: C.currency_icon(mb, "₿", m="LIB_Accent"), ["icon", "bitcoin", "crypto", "currency"],
    "Accent ₿. commerce_lib.currency_icon(mb, '₿', m=ACCENT)", bevel=0.005, az=-20)
add("icon_percent", lambda mb: C.currency_icon(mb, "%", m="LIB_Accent"), ["icon", "percent", "interest", "tax"],
    "commerce_lib.currency_icon(mb, '%')", bevel=0.005, az=-20)
add("icon_coin", lambda mb: C.coin_icon(mb, "$"), ["icon", "coin", "money"], "Display coin on edge (1 m). commerce_lib.coin_icon(mb, symbol, r)",
    bevel=0.004, az=-20)
add("icon_arrow_up", lambda mb: C.percent_arrow(mb, True), ["icon", "arrow", "growth", "up"],
    "Chunky trend arrow. commerce_lib.percent_arrow(mb, up=True)", bevel=0.01, az=-20)
add("icon_arrow_down", lambda mb: C.percent_arrow(mb, False, m="LIB_Dark"), ["icon", "arrow", "decline", "down"],
    "commerce_lib.percent_arrow(mb, up=False)", bevel=0.01, az=-20)

cat.finish(cols=6)
