import pandas as pd
from mlxtend.preprocessing import TransactionEncoder
from mlxtend.frequent_patterns import apriori, association_rules
import mysql.connector

# =========================
# STEP 1: LOAD DATASET
# =========================
df = pd.read_csv("grocery_transactions.csv")

# =========================
# STEP 2: CREATE TRANSACTIONS
# =========================
basket = df.groupby(['member_id', 'date'])['item'].apply(list)
basket = basket.reset_index()


# =========================
# STEP 3: ONE-HOT ENCODING
# =========================
te = TransactionEncoder()
te_data = te.fit(basket['item']).transform(basket['item'])

df_final = pd.DataFrame(te_data, columns=te.columns_)


# =========================
# STEP 4: APRIORI
# =========================
frequent_itemsets = apriori(df_final, min_support=0.003, use_colnames=True)

# =========================
# STEP 5: ASSOCIATION RULES
# =========================
rules = association_rules(frequent_itemsets, metric="confidence", min_threshold=0.02)

# =========================
# STEP 6: CLEAN FORMAT
# =========================
rules['antecedents'] = rules['antecedents'].apply(lambda x: ', '.join(list(x)))
rules['consequents'] = rules['consequents'].apply(lambda x: ', '.join(list(x)))

# =========================
# STEP 7: FILTER STRONG RULES 🔥
# =========================
rules = rules[(rules['confidence'] > 0.2) & (rules['lift']>1)]
rules= rules.sort_values(by='confidence',ascending=False).head(500)

# =========================
# STEP 8: KEEP REQUIRED COLUMNS
# =========================
rules = rules[['antecedents', 'consequents', 'support', 'confidence', 'lift']]

# =========================
# STEP 9: SAVE CSV
# =========================
rules.to_csv("rules2.csv", index=False)
print("CSV file created successfully ✔")

# =========================
# STEP 10: INSERT INTO MYSQL
# =========================

# 🔹 CONNECT DATABASE
conn = mysql.connector.connect(
    host="roundhouse.proxy.rlwy.net",
    user="root",
    password="yVAbOKBAMhyTiAXrgkzAgjxxmxhutANE",  # 🔴 replace with your password
    database="railway",
    port=17544
)

cursor = conn.cursor()

# 🔹 INSERT DATA
for _, row in rules.iterrows():
    query = """
    INSERT INTO association_rules (antecedents, consequents, support, confidence, lift)
    VALUES (%s, %s, %s, %s, %s)
    """
    values = (
        row['antecedents'],
        row['consequents'],
        float(row['support']),
        float(row['confidence']),
        float(row['lift'])
    )

    cursor.execute(query, values)

# 🔹 COMMIT & CLOSE
conn.commit()
cursor.close()
conn.close()

print("Rules inserted into Railway DB successfully")
print("Total length rules",len(rules))

