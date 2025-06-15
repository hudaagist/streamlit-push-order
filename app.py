import streamlit as st
import pandas as pd
import numpy as np
import requests
import json
from datetime import datetime
from requests.auth import HTTPBasicAuth
import concurrent.futures

# ==== CONFIG ====
UPLOAD_URL = 'https://oms.locus-api.com/v1/client/japfa-id-devo/order/'
UPDATE_BASE_URL = "https://lily-pre-prod.locus-api.com/oms/v1/client/japfa-id-devo/order/{}/line-item-update"


# ==== UTILITY FUNCTIONS ====

def format_date(date_str):
    return datetime.strptime(date_str, "%d.%m.%Y").strftime("%Y-%m-%d")

def convert_np_types(obj):
    if isinstance(obj, dict):
        return {k: convert_np_types(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_np_types(i) for i in obj]
    elif isinstance(obj, (np.integer, np.floating)):
        return obj.item()
    return obj


# ==== UI ====

st.title("📦 Locus Order Manager")

username = st.text_input("Username", placeholder="e.g., mara/personnel/hudaa")
password = st.text_input("Password", type="password")

tab1, tab2 = st.tabs(["📤 Upload Order", "✏️ Update Order"])

# === UPLOAD NEW ORDERS ===
with tab1:
    st.subheader("Upload New Orders")
    upload_file = st.file_uploader("Upload CSV for New Orders", type="csv", key="upload")

    if st.button("Submit New Orders"):
        if not upload_file:
            st.error("Please upload a CSV file.")
        elif not username or not password:
            st.error("Please enter username and password.")
        else:
            try:
                df = pd.read_csv(upload_file, encoding='utf-8-sig')
                df.columns = df.columns.str.strip()
                grouped = df.groupby("DO Number")
                requests_list = []

                for do_number, group in grouped:
                    document_date = format_date(group.iloc[0]["Document Date"])
                    plant = group.iloc[0]["Plant"]
                    ship_to = str(group.iloc[0]["Ship To"])
                    total_weight = 0.0
                    total_volume = 0.0
                    line_items = []
                    loose_items = []
                    line_item_counter = 1

                    for idx, row in group.iterrows():
                        material = str(row["Material"]).strip()
                        material_desc = str(row["Material Description"]).strip()
                        qty_kemasan = row.get("Qty Kemasan", "")
                        quantity = float(qty_kemasan) if pd.notnull(qty_kemasan) and str(qty_kemasan).strip() != '' else float(row["Qty SO in SU"])
                        weight = float(row["Qty SO in BU"])
                        volume = float(row["Qty SO in BU"])

                        line_items.append({
                            "customProperties": {
                                "kode-karung": "",
                                "kode-material": material,
                                "grouping": ""
                            },
                            "lineItemId": str(line_item_counter),
                            "skuId": material,
                            "name": material_desc,
                            "description": material_desc,
                            "unitsOfTransactions": [{"unitType": "QUANTITY"}, {"unitType": "WEIGHT"}],
                            "parts": [],
                            "attributes": {"quantity": quantity, "weight": weight, "volume": volume},
                            "attributesUnit": {
                                "quantityUnit": "PC", "weightUnit": "KG", "volumeUnit": "CM"
                            }
                        })

                        loose_items.append({
                            "lineItemId": str(line_item_counter),
                            "actualAttributes": {
                                "quantity": quantity,
                                "weight": weight,
                                "volume": volume
                            }
                        })

                        total_weight += weight
                        total_volume += volume
                        line_item_counter += 1

                    requests_list.append({
                        "id": do_number,
                        "type": "DROP",
                        "teamId": plant,
                        "homebaseId": plant,
                        "date": document_date,
                        "locationId": ship_to,
                        "orderDate": document_date,
                        "volume": {"value": total_volume, "unit": "CM"},
                        "weight": {"value": total_weight, "unit": "KG"},
                        "lineItemDetails": {
                            "lineItems": line_items,
                            "orderedDetail": {"loose": loose_items}
                        }
                    })

                payload = {"requests": convert_np_types(requests_list)}
                with st.spinner("Sending new order payload..."):
                    res = requests.post(
                        UPLOAD_URL,
                        json=payload,
                        auth=(username, password),
                        headers={"Content-Type": "application/json"}
                    )
                    st.success(f"Status Code: {res.status_code}")
                    try:
                        st.json(res.json())
                    except:
                        st.text(res.text)

            except Exception as e:
                st.error(f"Error: {e}")

# === UPDATE EXISTING ORDERS ===
with tab2:
    st.subheader("Update Existing Orders")
    update_file = st.file_uploader("Upload CSV for Order Updates", type="csv", key="update")

    if st.button("Submit Updates"):
        if not update_file:
            st.error("Please upload a CSV file.")
        elif not username or not password:
            st.error("Please enter username and password.")
        else:
            try:
                df = pd.read_csv(update_file, dtype=str)
                df.fillna("", inplace=True)
                df["QTY KEMASAN"] = df["QTY KEMASAN"].astype(float)
                df["KG KEMASAN"] = df["KG KEMASAN"].astype(float)

                order_groups = list(df.groupby("DO NO"))

                def send_update(order_tuple):
                    order_id, group = order_tuple
                    line_items = []
                    loose_items = []

                    for idx, row in group.iterrows():
                        line_item_id = idx + 1
                        sku_id = f"{row['MATERIAL']}-0000{row['DO ITEM']}"

                        line_items.append({
                            "customProperties": {
                                "kode-karung": row["KODE KARUNG"],
                                "kode-material": row["MATERIAL"],
                                "grouping": f"0000{row['DO ITEM']}"
                            },
                            "lineItemId": str(line_item_id),
                            "skuId": sku_id,
                            "name": row["MATERIAL DESCRIPTION"],
                            "description": row["MATERIAL DESCRIPTION"],
                            "unitsOfTransactions": [{"unitType": "QUANTITY"}, {"unitType": "WEIGHT"}],
                            "parts": [],
                            "attributes": {
                                "quantity": row["QTY KEMASAN"],
                                "weight": row["KG KEMASAN"],
                                "volume": 0
                            },
                            "attributesUnit": {
                                "quantityUnit": "PC", "weightUnit": "KG", "volumeUnit": "CM"
                            }
                        })

                        loose_items.append({
                            "lineItemId": str(line_item_id),
                            "actualAttributes": {
                                "quantity": row["QTY KEMASAN"],
                                "weight": row["KG KEMASAN"],
                                "volume": 0
                            }
                        })

                    payload = {
                        "lineItems": line_items,
                        "orderedDetail": {"loose": loose_items}
                    }

                    url = UPDATE_BASE_URL.format(order_id)
                    try:
                        response = requests.post(
                            url,
                            headers={"Content-Type": "application/json"},
                            auth=HTTPBasicAuth(username, password),
                            data=json.dumps(payload)
                        )
                        if response.status_code == 200:
                            return f"✅ Success for Order {order_id}"
                        else:
                            return f"❌ Failed for Order {order_id}: {response.status_code} - {response.text}"
                    except Exception as e:
                        return f"❌ Exception for Order {order_id}: {e}"

                st.info(f"Sending updates using 5 concurrent workers...")

                with st.spinner("Processing updates..."):
                    results = []
                    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                        futures = [executor.submit(send_update, group) for group in order_groups]
                        for future in concurrent.futures.as_completed(futures):
                            results.append(future.result())

                for res in results:
                    if res.startswith("✅"):
                        st.success(res)
                    else:
                        st.error(res)

            except Exception as e:
                st.error(f"Error: {e}")