"""Starting roster (100 Personalities) and the five house players."""

ROSTER = {
    "Music": [
        "Taylor Swift", "Beyoncé", "Drake", "Kendrick Lamar", "Bad Bunny", "Billie Eilish",
        "Olivia Rodrigo", "Sabrina Carpenter", "Dua Lipa", "The Weeknd", "Ariana Grande",
        "Travis Scott", "SZA", "Post Malone", "Morgan Wallen", "Zach Bryan", "Doja Cat",
        "Harry Styles", "Ed Sheeran", "Rihanna", "Lady Gaga", "Chappell Roan", "Bruno Mars",
        "Tyler, the Creator", "Charli XCX",
    ],
    "Sports": [
        "Patrick Mahomes", "Travis Kelce", "Josh Allen", "Lamar Jackson", "Joe Burrow",
        "LeBron James", "Stephen Curry", "Victor Wembanyama", "Nikola Jokić", "Caitlin Clark",
        "Shohei Ohtani", "Aaron Judge", "Lionel Messi", "Cristiano Ronaldo", "Erling Haaland",
        "Kylian Mbappé", "Lewis Hamilton", "Max Verstappen", "Scottie Scheffler", "Rory McIlroy",
        "Serena Williams", "Coco Gauff", "Carlos Alcaraz", "Simone Biles", "Connor McDavid",
    ],
    "Film & TV": [
        "Zendaya", "Timothée Chalamet", "Margot Robbie", "Ryan Reynolds", "Pedro Pascal",
        "Sydney Sweeney", "Glen Powell", "Florence Pugh", "Austin Butler", "Jenna Ortega",
        "Keanu Reeves", "Tom Holland", "Dwayne Johnson", "Jennifer Lawrence", "Leonardo DiCaprio",
        "Anya Taylor-Joy", "Jacob Elordi", "Ayo Edebiri", "Jeremy Allen White", "Meryl Streep",
    ],
    "Internet & Comedy": [
        "MrBeast", "Kai Cenat", "IShowSpeed", "Alix Earle", "Emma Chamberlain", "Logan Paul",
        "Bobbi Althoff", "Druski", "Nate Bargatze", "Shane Gillis", "Matt Rife", "Pete Davidson",
        "Ali Wong", "Bill Burr", "Kevin Hart",
    ],
    "Business & Tech": [
        "Jensen Huang", "Sam Altman", "Mark Zuckerberg", "Tim Cook", "Jeff Bezos",
        "Warren Buffett", "Oprah Winfrey", "Martha Stewart", "Kim Kardashian", "Kylie Jenner",
        "Selena Gomez", "Mark Cuban", "Gordon Ramsay", "Steven Bartlett", "Hailey Bieber",
    ],
}

CATEGORIES = list(ROSTER.keys())

# Each house player trades in its own style. Waking hours are local game time.
BOTS = [
    {"username": "jdub_trades", "strategy": "momentum", "wake": 7, "sleep": 23,
     "bio": "If it's going up I'm already in. Mahomes truther.", "email": "jdub.trades@example.com"},
    {"username": "meghan.k", "strategy": "contrarian", "wake": 8, "sleep": 24,
     "bio": "Buying everyone you're sleeping on. Patience pays.", "email": "meghan.k@example.com"},
    {"username": "bostonbrad44", "strategy": "ipo_flipper", "wake": 6, "sleep": 22,
     "bio": "Opening day guy. Get in, get out, get paid.", "email": "brad44@example.com"},
    {"username": "lowkeylarry", "strategy": "index", "wake": 9, "sleep": 25,
     "bio": "Diversified. Boring. Probably beating you.", "email": "lowkeylarry@example.com"},
    {"username": "sasha_bets", "strategy": "superfan", "wake": 10, "sleep": 26, "fav": "Music",
     "bio": "Pop girlies only. My portfolio has a soundtrack.", "email": "sasha.bets@example.com"},
]
