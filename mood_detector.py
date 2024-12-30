import requests
from textblob import TextBlob
import os
from datetime import datetime

class MoodDetector:
    def __init__(self):
        self.weather_api_key = os.getenv('OPENWEATHER_API_KEY')
        self.base_url = "http://api.openweathermap.org/data/2.5/weather"

    def get_weather_mood(self, city):
        """Get mood suggestions based on weather"""
        try:
            params = {
                'q': city,
                'appid': self.weather_api_key,
                'units': 'metric'
            }
            response = requests.get(self.base_url, params=params)
            weather_data = response.json()
            
            weather_moods = {
                'Clear': ['Happy', 'Energetic', 'Peaceful'],
                'Rain': ['Melancholic', 'Relaxed', 'Contemplative'],
                'Clouds': ['Calm', 'Focused', 'Mellow'],
                'Snow': ['Magical', 'Peaceful', 'Romantic'],
                'Thunderstorm': ['Intense', 'Dramatic', 'Energetic'],
            }
            
            weather_main = weather_data['weather'][0]['main']
            temp = weather_data['main']['temp']
            
            # Adjust mood based on temperature
            if temp > 25:  # Hot
                return ['Summer', 'Energetic', 'Party']
            elif temp < 10:  # Cold
                return ['Cozy', 'Calm', 'Introspective']
            
            return weather_moods.get(weather_main, ['Neutral'])
        except Exception as e:
            print(f"Error getting weather mood: {str(e)}")
            return ['Neutral']

    def analyze_text_mood(self, text):
        """Analyze mood from user's text input"""
        try:
            analysis = TextBlob(text)
            # Get polarity (-1 to 1) and subjectivity (0 to 1)
            polarity = analysis.sentiment.polarity
            subjectivity = analysis.sentiment.subjectivity
            
            # Map sentiment to moods
            if polarity > 0.5:
                return ['Excited', 'Happy', 'Energetic']
            elif polarity > 0:
                return ['Positive', 'Upbeat', 'Cheerful']
            elif polarity > -0.5:
                return ['Mellow', 'Calm', 'Relaxed']
            else:
                return ['Melancholic', 'Sad', 'Emotional']
        except Exception as e:
            print(f"Error analyzing text mood: {str(e)}")
            return ['Neutral']

    def get_time_based_mood(self):
        """Get mood suggestions based on time of day"""
        hour = datetime.now().hour
        
        if 5 <= hour < 9:
            return ['Morning', 'Energetic', 'Upbeat']
        elif 9 <= hour < 12:
            return ['Focused', 'Productive', 'Motivated']
        elif 12 <= hour < 15:
            return ['Relaxed', 'Calm', 'Peaceful']
        elif 15 <= hour < 18:
            return ['Upbeat', 'Energetic', 'Happy']
        elif 18 <= hour < 22:
            return ['Chill', 'Relaxed', 'Mellow']
        else:
            return ['Night', 'Calm', 'Peaceful']

    def combine_moods(self, text_input, city=None):
        """Combine different mood factors to get final mood suggestions"""
        moods = set()
        
        # Get moods from different sources
        if text_input:
            moods.update(self.analyze_text_mood(text_input))
        if city:
            moods.update(self.get_weather_mood(city))
        moods.update(self.get_time_based_mood())
        
        return list(moods)[:5]  # Return top 5 mood suggestions
