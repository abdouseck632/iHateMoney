DEBUG = False
SQLALCHEMY_DATABASE_URI = 'sqlite:///budget.db'
SQLACHEMY_ECHO = DEBUG
# Will likely become the default value in flask-sqlalchemy >=3 ; could be removed
# then:
SQLALCHEMY_TRACK_MODIFICATIONS = False

SECRET_KEY = "tralala"

MAIL_DEFAULT_SENDER = ("Budget manager", "budget@notmyidea.org")

ADMIN_PASS = ""

PUBLIC_PROJECT_CREATION = True
