# HomeGame 5.0

HomeGame 5.0 is a real-time, multiplayer No-Limit Texas Hold’em Poker platform powered by Django Channels, WebSockets, and LLM-driven poker bots.
It supports 22 human players, runs seamlessly in the browser, and allows each player to interact with a live game environment hosted on a scalable backend.

Also see the AI enhanced version with recaps, strategy, and playable LLM poker bots: [https://github.com/rtphawaii/HomeGameAI](https://github.com/rtphawaii/HomeGameAI)

## Demo & Gameplay
[https://vimeo.com/1131859523](https://vimeo.com/1134336089?share=copy&fl=sv&fe=ci)

## 🚀 Features

🎮 Real-time gameplay — built on Django 5 + Channels (ASGI) with Daphne and WebSockets for synchronized multiplayer.

📊 Poker Engine — full implementation of Texas Hold’em logic: betting rounds, blinds, pot management, and showdown resolution.

🌐 Web Frontend — clean, responsive HTML/CSS UI with a light minimal theme and animated elements for cards, chips, and player interactions.

🖥️ Production Ready — deployed on DigitalOcean using systemd, Nginx, and Gunicorn/Daphne with .env-based configuration.

## 🏗️ Tech Stack
Layer	Tools
Backend	Django 5.x, Channels, Daphne, ASGI
Frontend	HTML5, CSS3, Vanilla JS (WebSocket-driven)
Deployment	Nginx, systemd, DigitalOcean Ubuntu Droplet

## ⚙️ Local Setup
1️⃣ Clone and install dependencies
git clone https://github.com/<yourusername>/HomeGameAI.git
cd HomeGameAI/poker_site
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

2️⃣ Create .env file

Example:

DEBUG=True
SECRET_KEY=your_secret_key_here
ALLOWED_HOSTS=127.0.0.1,localhost
OPENROUTER_API_KEY=your_openrouter_api_key
GATE_PASSWORD=your_gate_password

3️⃣ Run migrations and collect static files
python manage.py migrate
python manage.py collectstatic --noinput

4️⃣ Run server locally
daphne -b 0.0.0.0 -p 8000 poker_site.asgi:application

