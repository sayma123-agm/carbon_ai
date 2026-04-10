import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
import joblib

# Generate dataset
np.random.seed(42)
size = 500

transport = np.random.randint(0, 100, size)
electricity = np.random.randint(0, 300, size)
food = np.random.choice([0, 1], size)  # 0 = veg, 1 = nonveg

co2 = (transport * 0.12) + (electricity * 0.82) + (food * 3)

df = pd.DataFrame({
    'transport': transport,
    'electricity': electricity,
    'food': food,
    'co2': co2
})

X = df[['transport', 'electricity', 'food']]
y = df['co2']

# Train model
model = RandomForestRegressor(n_estimators=100)
model.fit(X, y)

# Save model
joblib.dump(model, 'carbon_model.pkl')

print("✅ Model trained and saved!")