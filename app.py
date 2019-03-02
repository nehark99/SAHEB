from flask_restful import Resource, Api
from deeppavlov import build_model, configs
from nltk import word_tokenize

from flask import Flask, jsonify, render_template, request, flash, redirect, url_for, session
from flask_cors import CORS
from wtforms import Form, StringField, PasswordField, validators
from passlib.hash import sha256_crypt
from functools import wraps

from substitute_data import InsertData, UpdateData, ReadData, DeleteData
from paragraph_api import Paragraph
import sqlite3
from nltk.corpus import stopwords
from string import punctuation
import re



app = Flask(__name__)
CORS(app)
api = Api(app)

model = None
paragraph = None
values = dict()


class HelloWorld(Resource):
    def get(self):
        return {'hello': 'world'}


@app.route('/hello/')
def hello_world():
    return 'Hello, World!'


@app.before_first_request
def init_stuff():
    """
    Initialize the data and the model before first request is processed.
    :return: None
    """
    load_data()
    # load_model()


class ChatBot(Resource):
    def post(self):
        threshold = 45000
        minimum_match = 1

        question = request.form['question']
        question = question.strip()
        question = question
        if question[-1] != "?":
            question += '?'
        print(question)
        answer = model([paragraph], [question])
        print(answer)
        answer_main = answer[0][0]

        keys = re.findall('zxyw[^\s.]*', answer_main)
        if keys:
            print(keys)
            for k in keys:
                answer_main = re.sub(k, values[k[4:]], answer_main)
        print(answer_main)

        if answer[2][0] < threshold:
            question_list = removeStopWords(question)
            answer_list = removeStopWords(answer_main)
            print(question_list,answer_list)
            count = 0
            for i in question_list:
                for j in answer_list:
                    if i == j:
                        count += 1
            if count >= minimum_match:
                return answer_main
            else:
                return "Sorry i didn't get that!"
        else:
            return answer_main


def load_model():
    # load the model into memory
    global model
    model = build_model(configs.squad.squad, download=False)


def removeStopWords(words):
    customStopWords = set(stopwords.words('english') + list(punctuation))
    return [word for word in word_tokenize(words) if word not in customStopWords]


def load_data():
    # DONE (3) load the paragraph and all the key-value pairs into the global variables
    global paragraph
    global values
    para_sql = "select * from paragraph;"
    values_sql = "select * from blank_data;"
    try:
        conn = sqlite3.connect('test.db')
        cursor = conn.cursor()
        cursor.execute(para_sql)
        paragraph = cursor.fetchall()[0][0]
        cursor.execute(values_sql)
        values_list = cursor.fetchall()

        for i in values_list:
            values.update({i[1]: i[2]})

        print(paragraph)
        print(values)

    except Exception as e:
        print(e)
    finally:
        if conn:
            conn.close()


# check if user is logged in
def is_logged_in(f):
    @wraps(f)
    def wrap(*args, **kwargs):
        print(session['logged_in'])
        if 'logged_in' in session:
            return f(*args, **kwargs)
        else:
            flash('Unauthorized, Please login', 'danger')
            return redirect(url_for('login'))
    return wrap


@app.route('/', methods=['GET', 'POST'])
def index():
    if 'logged_in' in session:
        if session['logged_in']:
            return redirect('/para/')
    else:
        return render_template('login.html')


@app.route('/key_values/')
@is_logged_in
def admin_page():
    return render_template('key_vals.html', js_files=['key-val.js', ])


@app.route('/read/values/')
@is_logged_in
def read_values():
    formatted_data = []
    try:
        connection = sqlite3.connect('test.db')
        c = connection.cursor()
        c.execute('SELECT * FROM blank_data')
        table_data = c.fetchall()
        for items in table_data:
            formatted_data.append(dict(id=items[0], key=items[1], value=items[2]))
        connection.commit()
        resp = jsonify(formatted_data)
    except Exception as exception:
        print(exception)
        resp = jsonify(success=False)
    finally:
        if connection:
            connection.close()
    return resp


@app.route('/edit_para/', methods=['POST', 'GET'])
@is_logged_in
def edit_para():
    if request.form['str']:
        new_paragraph = request.form['str']
        print(new_paragraph)
    try:
        conn = sqlite3.connect('test.db')
        c = conn.cursor()
        c.execute('UPDATE paragraph SET para="' + new_paragraph + '";')
        # conn.commit()
        keys_para = re.findall('zxyw[^\s.]*]', new_paragraph)
        c.execute('SELECT key FROM blank_data')
        keys_db = c.fetchall()
        for item in keys_para:
            if item not in keys_db:
                c.execute("DELETE FROM blank_data WHERE key='"+item+"';")
        conn.commit()

        c.execute('select * from paragraph;')
        new_paragraph = c.fetchall()
    except Exception as exception:
        print(exception)

    finally:
        if conn:
            conn.close()

    return new_paragraph


@app.route('/update/values/', methods=['POST', ])
@is_logged_in
def update_values():
    try:
        connection = sqlite3.connect('test.db')
        c = connection.cursor()
        if request.form['id'] and request.form['value']:
            i = request.form['id']
            value = request.form['value']
            sql = 'update blank_data set `value` = "'+value+'" where `id` = "'+i+'";'
            c.execute(sql)
            connection.commit()
            resp = jsonify(success=True, id=i, value=value)
    except Exception as exception:
        print(exception)
        resp = jsonify(success=False)
    finally:
        if connection:
            connection.close()
        return resp


@app.route('/insert/values/', methods=['POST', ])
@is_logged_in
def insert_values():
    if request.form['key'] and request.form['value']:
        key = request.form['key']
        value = request.form['value']
        try:
            connection = sqlite3.connect('test.db')
            c = connection.cursor()
            sql = 'INSERT INTO blank_data (`key`, `value`) VALUES("' + key + '", "' + value + '");'
            c.execute(sql)
            connection.commit()
            sql = 'select * from blank_data where `key` = "'+key+'";'
            c.execute(sql)
            data = c.fetchall()
            formatted_data = {"id": data[0][0], "key": data[0][1], "value": data[0][2]}
            resp = jsonify(success=True, data=formatted_data)
        except sqlite3.IntegrityError as e:
            print(e)
            resp = jsonify(success=False, error="Key already exists!")
        finally:
            if connection:
                connection.close()
        return resp


@app.route('/delete/values', methods=['POST', ])
@is_logged_in
def delete_values():
    if request.form['key']:
        key = request.form['key']

        try:
            connection = sqlite3.connect('test.db')
            c = connection.cursor()
            sql = 'delete from blank_data where `key` = "'+key+'";'
            c.execute(sql)
            connection.commit()
            resp = jsonify(success=True)
        except Exception as e:
            print(e)
            resp = jsonify(success=False)
        finally:
            if connection:
                connection.close()
            return resp


@app.route('/para/')
@is_logged_in
def read_para():
    try:
        conn = sqlite3.connect('test.db')
        c = conn.cursor()
        c.execute('select * from paragraph')
        paragraph = c.fetchall()
        conn.commit()
    except sqlite3.IntegrityError:
        return {"error"}
    except Exception as exception:
        print(exception)
    finally:
        if conn:
            conn.close()
    return render_template('view_para.html', para = paragraph[0][0], js_files=['para.js', ])




# register form class
class RegisterForm(Form):
    name = StringField('Name', [validators.Length(min=1, max=50)])
    # username = StringField('Username', [validators.Length(min=4, max=25)])
    email = StringField('Email', [validators.Length(min=6, max=50)])
    password = PasswordField('Password', [
        validators.DataRequired(),
        validators.EqualTo('confirm', message='Password do not match')
    ])
    confirm = PasswordField('Confirm Password')


# user register
@app.route('/register', methods=['GET', 'POST'])
@is_logged_in
def register():
    form = RegisterForm(request.form)
    if request.method == 'POST' and form.validate():
        name = form.name.data
        email = form.email.data
        # username = form.username.data
        password = sha256_crypt.encrypt(str(form.password.data))

        try:
            connection = sqlite3.connect('test.db')
            cursor = connection.cursor()
            cursor.execute("INSERT INTO users(name,email,password) VALUES('"+name+"','"+email+"','"+password+"')")
            connection.commit()
            connection.close()
            return redirect(url_for('dashboard'))
        except sqlite3.IntegrityError as ie:
            print(ie)
        except Exception as e:
            print(e)

    return render_template('register.html', form=form)


# User Login
@app.route('/login/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password_candidate = request.form['password']

        connection = sqlite3.connect('test.db')
        cursor = connection.cursor()
        result = cursor.execute("SELECT * FROM users WHERE email = '"+email+"'")
        print(result.fetchall())
        if result.arraysize > 0:
            data = result.fetchall()
            print(data)
            password = data[2]
            if sha256_crypt.verify(password_candidate, password):
                app.logger.info('PASSWORD MATCHED')
                session['logged_in'] = True
                session['email'] = email

                flash('You are now logged in', 'success')

                return redirect('/para/')

            else:
                app.logger.info('PASSWORD NOT MATCHED')
                error = 'Incorrect Password'
                return render_template('login.html', error=error)

            cursor.close()
        else:
            app.logger.info('NO USER')
            error = 'Username not found'
            return render_template('login.html', error=error)

    return render_template('login.html')





# logout
@app.route('/logout')
@is_logged_in
def logout():
    session.clear()
    flash('You are now logged out ', 'success')
    return redirect(url_for('login'))


api.add_resource(ChatBot, '/chat/')


if __name__ == '__main__':
    app.secret_key = 'qwertyuuiop'
    app.run(host='127.0.0.1', port=5000, debug=True)
