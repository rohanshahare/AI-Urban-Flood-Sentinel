\# Flood Risk Assessment Engine



\## Objective

To estimate flood risk for drainage locations using blockage severity, rainfall intensity, and historical vulnerability.



\## Methodology

1\. Normalize the blockage percentage, rainfall measurements, and historical vulnerability.

2\. Assign weights to the risk factors.

3\. Calculate a weighted flood-risk score.

4\. Map the score to a risk category: LOW, MODERATE, HIGH, or CRITICAL.

5\. Generate recommendations based on the estimated risk.

6\. Return warnings when input data is missing or synthetic.



\## Risk Factor Weights

\- Blockage severity: 45%

\- Rainfall intensity: 35%

\- Historical vulnerability: 20%



\## Data Limitations

The historical dataset contains synthetic data for development and testing. Results are estimates and must not be treated as verified real-world flood predictions.



\## Testing

The engine and history-analysis tests are run using Python test scripts. Scenario testing is performed using `what\_if.py`.



\## Expected Outcome

Provide a consistent flood-risk assessment and actionable recommendations for drainage maintenance and inspection.

