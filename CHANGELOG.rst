Changelog
=========

This document describes changes between each past release.

2.0 (unreleased)
----------------

### Breaking Changes

- Use a hashed ``ADMIN_PASSWORD`` instead of a clear text one, ``./budget/manage.py generate_password_hash`` can be used to generate a proper password HASH (#236)
- Turn the WSGI file into a python module, renamed from budget/ihatemoney.wsgi to budget/wsgi.py. Please update your Apache configuration!
- Admin privileges are required to access the dashboard

### Changed

- Changed the recommended gunicorn configuration to use the wsgi module as an entrypoint

### Added

- Add a new setting to allow public project creation (ALLOW_PUBLIC_PROJECT_CREATION)
- With admin credentials, one can access every project
- Add delete and edit project actions in the dashboard
- Add a new setting to activate the dashboard (ACTIVATE_ADMIN_DASHBOARD)
- Add a link to the dashboard in the navigation bar when it is activated

### Removed

- Remove unused option in the setup script

1.0 (2017-06-20)
----------------

### Added

- Apache WSGI Support (#191)
- Brush up the Makefile (#207, #201)
- Externalize the settings from source folder (#193)
- Makefile: Add new rule to compile translations (#207)
- Project creation can be restricted to admin (#210)
- More responsive layout (#213)

### Changed

- Some README enhancements
- Move tests to budget.tests (#205)
- The demo project can be disabled (#209)

### Fixed

- Fix sphinx integration (#208)

0.9 (2017-04-04)
----------------

- First release of the project.
