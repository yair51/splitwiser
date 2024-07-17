from flask_login import UserMixin
from . import db

# Association table for the many-to-many relationship between User and Group
user_group = db.Table('user_group',
                      db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
                      db.Column('group_id', db.Integer, db.ForeignKey('group.id'), primary_key=True)
                      )


class User(UserMixin, db.Model):
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(100), unique=True, nullable=False)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    password = db.Column(db.String(250), nullable=False)
    groups = db.relationship('Group', secondary=user_group, backref=db.backref('members', lazy=True))

    def __repr__(self):
        return f'<User {self.email}>'


class Group(db.Model):
    __tablename__ = 'group'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    expenses = db.relationship('Expense', backref='group', lazy=True)  # Relationship with expenses

    def __repr__(self):
        return f'<Group {self.name}>'


class Expense(db.Model):
    __tablename__ = 'expense'
    id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.String(200), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    date = db.Column(db.Date, nullable=False)
    group_id = db.Column(db.Integer, db.ForeignKey('group.id'), nullable=False)
    paid_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    paid_by = db.relationship('User', foreign_keys=[paid_by_id])  # Who paid the expense

    def __repr__(self):
        return f'<Expense {self.description}: {self.amount}>'

# Additional models you might consider:
# class Debt(db.Model):   # To track debts between users in a group 
# class Payment(db.Model): # To track payments made towards debts
