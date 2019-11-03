import os
import pickle
import logging


class AuthManager:
    def __init__(self, password):
        self.logging = logging.getLogger(__name__)
        self.password = password
        self.users = set()

        self.load()

    def is_authorized(self, user_id):
        return user_id in self.users

    def authorize(self, user_id, password):
        is_ok = password == self.password

        self.logging.info(f'authorize {user_id} with {password}: {is_ok}')

        if is_ok:
            self.users.add(user_id)
            self.save()

        return is_ok

    def save(self):
        with open('users.pickle', 'wb') as f:
            pickle.dump(self.users, f)

    def load(self):
        if not os.path.exists('users.pickle'):
            return

        with open('users.pickle', 'rb') as f:
            self.users = pickle.load(f)
