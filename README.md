# Weather Application

A command-line weather application that retrieves current weather data using the OpenWeatherMap API, with support for city names or postal codes and international country resolution.

The project is structured with a client-side application and a lightweight proxy service to securely manage API credentials and enforce request limits.

---

## Documentation

For the full explanation of how this project works, see [Weather Application Documentation](./DOCUMENTATION.md).

---

## Features

- Retrieve current weather by:
  - City name + country
  - Postal / ZIP code + country
- Interactive country selection using ISO 3166 standards
- Secure API key handling via a proxy service
- Rate limiting and global daily request limits
- Clear separation between client logic and network access

---


