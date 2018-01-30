#!/bin/sh
cat <<EOF >> /etc/ihatemoney/ihatemoney.cfg
DEBUG = $DEBUG
SQLALCHEMY_DATABASE_URI = "$SQLALCHEMY_DATABASE_URI"
SQLACHEMY_DEBUG = DEBUG
SQLALCHEMY_TRACK_MODIFICATIONS = $SQLALCHEMY_TRACK_MODIFICATIONS
SECRET_KEY = "$SECRET_KEY"
MAIL_SERVER = "$MAIL_SERVER"
MAIL_PORT = $MAIL_PORT
MAIL_USE_TLS = $MAIL_USE_TLS
MAIL_USE_SSL = $MAIL_USE_SSL
MAIL_USERNAME = "$MAIL_USERNAME"
MAIL_PASSWORD = "$MAIL_PASSWORD"
MAIL_DEFAULT_SENDER = "$MAIL_DEFAULT_SENDER"
ACTIVATE_DEMO_PROJECT = $ACTIVATE_DEMO_PROJECT
ADMIN_PASSWORD = "$ADMIN_PASSWORD"
ALLOW_PUBLIC_PROJECT_CREATION = $ALLOW_PUBLIC_PROJECT_CREATION
ACTIVATE_ADMIN_DASHBOARD = $ACTIVATE_ADMIN_DASHBOARD
EOF
# Start gunicorn without forking
exec gunicorn ihatemoney.wsgi:application \
     -b 0.0.0.0:8000 \
     --log-syslog \
     "$@"
