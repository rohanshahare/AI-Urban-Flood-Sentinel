# System Architecture

## Intended flow

1. The user selects or uploads a drain image.
2. The backend validates the request.
3. The vision component analyzes the image.
4. The risk engine evaluates blockage evidence alongside available
   rainfall and contextual information.
5. The backend combines the results.
6. The frontend presents results, locations, and alerts.

## Component ownership

- Vision: Rohan
- Risk engine: Sanket
- Backend integration: Risheeth
- Frontend and GIS: Samrudh

The implementation and component interfaces must be confirmed
with the relevant team members.
