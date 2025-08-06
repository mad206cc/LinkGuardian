<<<<<<< HEAD
# En résumé, ce script écoute en continu la file d'attente RabbitMQ ('site_check_queue') et traite de manière asynchrone les messages reçus en appelant la fonction process_site. 
# Cela permet de mettre à jour les informations des sites dans la base de données en fonction des résultats des vérifications de liens et d'indexation Google.


import pika
import json
import asyncio
from aiohttp import ClientSession
from app import app, check_link_presence_and_follow_status_async, check_google_indexation, import_data  # Importez l'instance de l'application Flask
from models import db, Website
from datetime import datetime
from sqlalchemy import desc
from flask import jsonify
from flask_socketio import SocketIO
from flask import Flask, request, jsonify


socketio = SocketIO(app)

async def process_site(data):
    with app.app_context(): 
        async with ClientSession() as session:
           
            url = data["url"]
            link_to_check = data["link_to_check"]
            anchor_text = data["anchor_text"]

           
            link_data = await check_link_presence_and_follow_status_async(session, url, link_to_check, anchor_text)
            index_status = await check_google_indexation(session, url)


            link_present, anchor_present, follow_status = link_data

            site = Website.query.filter_by(url=url).order_by(desc(Website.last_checked)).first()

            if site:
               
                old_site = Website(url=site.url,
                                   link_to_check=site.link_to_check,
                                   anchor_text=site.anchor_text,
                                   link_status=site.link_status,
                                   link_follow_status=site.link_follow_status,
                                   anchor_status=site.anchor_status,
                                   google_index_status=site.google_index_status,
                                   source_plateforme= site.source_plateforme,
                                   last_checked=site.last_checked,
                                   user_id= site.user_id,
                                   page_value= site.page_value,
                                   page_trust= site.page_trust,
                                   bas= site.bas,
                                   backlinks_external= site.backlinks_external,
                                   num_outlinks_ext= site.num_outlinks_ext,
                                   status_code= site.status_code,
                                   tag= site.tag
                                   )

                site.link_status = "Lien présent" if link_present else "URL non présente"
                site.link_follow_status = follow_status if link_present else None
                site.anchor_status = "Ancre présente" if anchor_present else "Ancre manquante"
                site.google_index_status = index_status
                site.last_checked = datetime.utcnow()
                db.session.commit()

                db.session.add(old_site)
                db.session.commit()
                
            await asyncio.sleep(1) 
            
        return jsonify({"message": "Traitement terminé"}) 
        
    

def callback(ch, method, properties, body):
    data = json.loads(body)
    asyncio.run(process_site(data))

connection = pika.BlockingConnection(pika.ConnectionParameters('localhost'))
channel = connection.channel()
channel.queue_declare(queue='site_check_queue')

channel.basic_consume(queue='site_check_queue',
                      on_message_callback=callback,
                      auto_ack=True)

print(' [*] En attente de messages. Pour quitter, pressez CTRL+C')
channel.start_consuming()
=======
# myapp/consumer.py
# Assurez-vous que DJANGO_SETTINGS_MODULE est défini avant d'importer quoi que ce soit de Django
import os
import pika
import json
import django
import time
import pandas as pd
from datetime import datetime
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'SEO_Prediction_Project.settings')
django.setup()

import pika
import json
from SEO_Prediction_App.models import User, Keyword,Test, Data, MinMaxValue, UrlPredected, MinMaxUrlValue, AnalysUrlResult
from import_data_url import import_data_url_from_csv_files
from SEO_Prediction_App.models import AnalysisResult
from Predictive.train_Models import TrainModels
from Predictive.response_Builder import ResponseBuilder
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from django.contrib.auth import get_user_model
from django.contrib.auth.models import User 
from django.db.models import Max
from django.conf import settings
import SEO_Prediction_App.test as test
from Predictive.url_Predict import UrlPredect
import pickle

User = get_user_model()
def process_message(ch, method, properties, body):
    message = json.loads(body)
    
    message_type = message.get('type')
    data = message.get('data')
    
    print("the message type is :", message_type)

    if message_type == 'keyword':
        keyword_searched = data.get('keyword')
        email = data.get('email')
        user_id = data.get('user_id')

        user_instance = User.objects.get(id=user_id)
        handle_keywords(keyword_searched, email, user_instance)

    if message_type == 'url':
        selected_keyword = data.get('selected_keyword')
        entered_url = data.get('entered_url')
        user_id = data.get('user_id')

        user_instance = User.objects.get(id=user_id)
        handle_url(selected_keyword, entered_url, user_instance)
        
    ch.basic_ack(delivery_tag=method.delivery_tag)

def handle_keywords(keyword_searched, email, user_instance): 
    
    expediteur = 'damienhernandez0@gmail.com'
    mot_de_passe = 'ceeeiennsmzyuhfg'
    destinataire = email
    objet = 'Analyse predictive ranking'
    corps_message = f"Bonjour, une analyse sur le prédictive ranking a été créée.\n Bien cordialemment"

    message = MIMEMultipart()
    message['From'] = expediteur
    message['To'] = destinataire
    message['Subject'] = objet
    message.attach(MIMEText(corps_message, 'plain'))
    serveur_smtp = smtplib.SMTP('smtp.gmail.com', 587)
    serveur_smtp.starttls()
    serveur_smtp.login(expediteur, mot_de_passe)
    serveur_smtp.send_message(message)
    serveur_smtp.quit()
    
    test.run_script_with_keyword(keyword_searched,user_instance)
        
    # Initialisation de la classe TrainModels
    trainer = TrainModels()
    response_builder = ResponseBuilder()
    trainer.keyword = keyword_searched
    print("****************************Trainer.keyword is ***********************", trainer.keyword)

    # Read data from Data Base
    trainer.read_my_data()
    colonnes_exclues = ['Keyword','Url']
    trainer.df = trainer.df.drop(columns=colonnes_exclues, errors='ignore')
    trainer.df = trainer.data_to_drop(trainer.df)
    trainer.preprocessing()

    print(trainer.df)
        
    #trainer.df = trainer.df.drop(columns=["Keyword"])
    trained_models, X_train, y_train, X_test, y_test=trainer.Final_get_importance(user_instance)
    response_builder.trainedModels= trained_models
    response_builder.df = trainer.df
    response_builder.trainedModels.X = X_train
    response_builder.trainedModels.y = y_train

    min_max = response_builder.get_min_max()
        
        
    # Récupérer l'ID du test le plus récent pour le mot-clé spécifié
    latest_test_id = Test.objects.filter(Keyword=keyword_searched).aggregate(latest_id=Max('id'))['latest_id']

    #Récupération des données pour les graphs en courbe
    if latest_test_id:
        # Récupérer le test correspondant à l'ID le plus récent
        test_instance = Test.objects.get(id=latest_test_id)

        # Obtenez les noms de champs et leurs valeurs depuis la base de données
        fields_and_values = {}
        for field in Test._meta.get_fields():
            field_name = field.name
            field_value = getattr(test_instance, field_name)
            # Supprimer '_score' du nom de champ et remplacer '_' par un espace
            display_field_name = field_name.replace('_score', '').replace('_', ' ')
            if isinstance(field_value, (int, float)):
                field_value = round(field_value, 2)
                fields_and_values[display_field_name] = field_value


        # Filtrer les champs qui sont des entiers ou des flottants et ont une valeur supérieure à 0
        results = [(field_name, field_value) for field_name, field_value in fields_and_values.items() if isinstance(field_value, (int, float)) and field_value > 0.0]
        results = sorted(results, key=lambda x: x[1], reverse=True)[:15]

        # Récupérer tous les noms de champ à partir de results
        champs = [field_name for field_name, _ in results]
          
        # Récupérer les valeurs de l'attribut à partir du quatrième champ pour chaque objet dans la base de données filtrés par keyword_searched
        valeurs_attributs_a_partir_de_4_yes = [] 
        valeurs_attributs_a_partir_de_4_no = [] 

        # Restaurer les noms de champ en supprimant les remplacements précédents
        champs_restaurés = [field_name.replace(' ', '_').replace('_score', '_') for field_name in champs]
        # Liste des colonnes à exclure
        columns_to_exclude = ["id", "nb_url", "precision"]
        # Déterminer les colonnes à conserver
        set_champs = set(champs_restaurés)
        set_exclude = set(columns_to_exclude)
        set_min_max = set(min_max)

        columns_to_keep = list(set_champs - set_exclude & set_min_max)
        # Alternativement, vous pouvez utiliser une compréhension de liste si vous préférez rester avec des listes
        columns_to_keep = [field for field in champs_restaurés if field not in columns_to_exclude and field in min_max]

        # Filtrer min_max pour ne conserver que les clés de columns_to_keepzs
        min_max_filtered = {key: min_max[key] for key in columns_to_keep}

        print("min_max_filtered:", min_max_filtered)
            
        results_with_min_max = []
        for field_name, field_value in results:
            # Obtenir les valeurs min-max en tant que chaîne
            min_max_series = min_max_filtered.get(field_name.replace(' ', '_'), None)
            min_max_str = str(min_max_series.values[0]) if min_max_series is not None else "N/A"  # Exclure les métadonnées comme index
            results_with_min_max.append((field_name, field_value, min_max_str))
           
        print("j'affiche results_with_min_wmax, afin d'envoyer vers le front-end et les afficher",results_with_min_max)  

        # Boucle à travers les résultats pour créer et enregistrer les valeurs min_max
        for attribute_name, attribute_value, min_max_value in results_with_min_max:
            # Créez une instance de MinMaxValue associée à l'instance de Test
            min_max_instance = MinMaxValue.objects.create(
                test_instance=test_instance,
                attribute_name=attribute_name,
                attribute_value=attribute_value,
                min_max=min_max_value  # Utilisez le champ 'min_max' au lieu de 'min_max_value'
            )
            # Enregistrez l'instance dans la base de données
            min_max_instance.save()
            
        #print("DataFrame filtré avec les colonnes de 'results':", min_max_filtered)
        for objet in Data.objects.filter(Keyword=keyword_searched, Top10=True):
            # Récupérer les valeurs de tous les attributs à partir du quatrième champ
            valeurs_attributs = [getattr(objet, field_name) for field_name in champs_restaurés[4:]]  # Utilisez tous les champs à partir du quatrième
            valeurs_attributs_a_partir_de_4_yes.append(valeurs_attributs)

        # Parcourir les huit premiers attributs à partir du 4eme
        for index, attribut in enumerate(champs_restaurés[4:15], start=4):
            #print(f"Valeurs de l'attribut '{attribut}' pour Top10 = Yes:")
            for valeurs in valeurs_attributs_a_partir_de_4_yes:
                if len(valeurs) > index - 4:  # Index relatif à la position dans champs_restaurés
                     print(valeurs[index - 4])
                else:
                    print("Aucune valeur disponible")
            print("\n")


        for objet in Data.objects.filter(Keyword=keyword_searched, Top10=False):
            # Récupérer les valeurs de tous les attributs à partir du quatrième champ
            valeurs_attributs = [getattr(objet, field_name) for field_name in champs_restaurés[4:]]  # Utilisez tous les champs à partir du quatrième
            valeurs_attributs_a_partir_de_4_no.append(valeurs_attributs)

        # Parcourir les huit premiers attributs à partir du 4eme
        for index, attribut in enumerate(champs_restaurés[4:15], start=4):
            #print(f"Valeurs de l'attribut '{attribut}' pour Top10 = No:")
            for valeurs in valeurs_attributs_a_partir_de_4_no:
                if len(valeurs) > index - 4:  # Index relatif à la position dans champs_restaurés
                    print("valeurs[index - 4]")
                else:
                    print("Aucune valeur disponible")
            print("\n")


            # Organiser les données
        data_for_charts = []
        for index, attribut in enumerate(champs_restaurés[3:15], start=3):
            values_yes = [v[index - 4] for v in valeurs_attributs_a_partir_de_4_yes if v[index - 4] is not None]
            values_no = [v[index - 4] for v in valeurs_attributs_a_partir_de_4_no if v[index - 4] is not None]
            data_for_charts.append({'attribut': attribut, 'yes': values_yes, 'no': values_no})


            #print("What im going to send",data_for_charts)

           
        data_for_charts_json = json.dumps(data_for_charts) 

    handle_result(keyword_searched, email, user_instance, results, data_for_charts_json, results_with_min_max)
    # Envoi de l'e-mail
    expediteur = 'damienhernandez0@gmail.com'
    mot_de_passe = 'ceeeiennsmzyuhfg'
    destinataire = email
    objet_terminer = "Analyse predictive ranking terminée"
    corps_message_terminer = f"L'analyse pour le mot-clé '{keyword_searched}' est terminée. Vous pouvez maintenant consulter les résultats."

    message = MIMEMultipart()
    message['From'] = expediteur
    message['To'] = destinataire
    message['Subject'] = objet_terminer
    message.attach(MIMEText(corps_message_terminer, 'plain'))
    serveur_smtp = smtplib.SMTP('smtp.gmail.com', 587)
    serveur_smtp.starttls()
    serveur_smtp.login(expediteur, mot_de_passe)
    serveur_smtp.send_message(message)
    serveur_smtp.quit()
     


def handle_result(keyword_searched, email, user_instance, results, data_for_charts_json, results_with_min_max):
    current_datetime = datetime.now()
    current_date = current_datetime.date()
    current_time = current_datetime.time()

    print(f"Handling result for keyword: {keyword_searched}, email: {email}, user: {user_instance}, date_test: {current_date}, hour_test: {current_time}")
    
    AnalysisResult.objects.create(
        user=user_instance,
        keyword=keyword_searched,
        results=results,
        data_for_charts_json=data_for_charts_json,
        results_with_min_max=results_with_min_max,
        date_test=current_date,
        hour_test=current_time
    )
    
    print("Analysis result successfully recorded")
    return results, data_for_charts_json, results_with_min_max


def handle_url(selected_keyword, entered_url, user_instance):
    # Traitez les données ici et ajoutez la logique appropriée

        response_builder = ResponseBuilder()
        trainer = TrainModels()
        up = UrlPredect()

        specific_url = entered_url
        keyword = selected_keyword

        # Lecture de la data depuis la bdd
        trainer.keyword = keyword
        df = trainer.read_my_data()
        trainer.df = df
        print("**************Trainer_df**************", trainer.df)

        trainer.df = trainer.df.drop(columns=["Keyword"])
        trainer.df = trainer.df.drop(columns=["Url"])
        trainer.df = trainer.data_to_drop(trainer.df)
        trainer.preprocessing()
        print(trainer.df)

        response_builder.df = trainer.df
        print(response_builder.df)

        X_train, X_test, y_train, y_test = trainer.split_data(trainer.X, trainer.y)

        trained_model = trainer.train_XGBClassifier(X_train, y_train)
        auc, acc = trainer.eval_model(trained_model, X_test, y_test)
        print(auc, acc)
        df_importance = trainer.get_importance(trained_model)
        df_importance_top_15 = df_importance.head(15)
        print("Les 15 fonctionnalités les plus importantes :")
        print(df_importance_top_15)

        trained_model.y = y_train
        response_builder.trainedModels = trained_model

        data_test, testing = up.get_data_for_1_urls(specific_url, keyword, df, response_builder)

        if not testing:
            csv_filename = './Url_data/url_data_output.csv'
            up.url_data.to_csv(csv_filename, index=False)
            print(f"Data saved to {csv_filename}")

            data_sets = "./Url_data"
            import_data_url_from_csv_files(data_sets)

        thedf_test = up.get_data_url_from_database()
        print("j'affiche the dftest",thedf_test)

        up.url_data = thedf_test
        up.url_data = up.exclude_and_convert_columns(up.url_data)
        result, pred_res = up.try_for_columns(trained_model, response_builder)
        print(pred_res)

        if pred_res is not None:
            if pred_res > 0.5:
                top10_value = True
            else:
                top10_value = False
        else:
            top10_value = False 

        df_min_max = response_builder.get_min_max_url()
        # Filtrer les résultats pour ne conserver que les 15 premières fonctionnalités importantes
        top_15_columns = df_importance_top_15['variable'].tolist()
        df_min_max_top_15 = df_min_max[top_15_columns]
    
        # Convertir en liste de dictionnaires
        df_min_max_top_15_list = df_min_max_top_15.reset_index().melt(id_vars=['index']).to_dict(orient='records')
        for i, row in enumerate(df_min_max_top_15_list):
           row['index'] = i + 1
        
        # Convertir thedf_test en liste de dictionnaires
        thedf_test_list = thedf_test.to_dict(orient='records')

        top_15_column_names = [row['variable'] for row in df_min_max_top_15_list]
        # Créez une nouvelle liste pour stocker les dictionnaires filtrés
        filtred_thedf_test_list = []

        # Parcourir chaque ligne de thedf_test_list
        for row in thedf_test_list:
            # Créez un nouveau dictionnaire pour stocker les valeurs filtrées
            filtered_row = {}
            # Parcourez chaque clé (nom de colonne) dans la ligne
            for key in row.keys():
                # Si la clé est également dans les noms de colonnes top_15_column_names
                if key in top_15_column_names:
                    # Ajoutez cette paire clé-valeur au dictionnaire filtré
                    filtered_row[key] = row[key]
            # Ajoutez le dictionnaire filtré à la liste de résultats
            filtred_thedf_test_list.append(filtered_row)
        
        # Puisque l'index a été mis à jour, vous pouvez l'utiliser maintenant dans la boucle suivante
        for row in df_min_max_top_15_list:
            # Récupérez le nom de la variable dans df_min_max_top_15_list
            variable_name = row['variable']
            # Parcourez chaque dictionnaire dans filtred_thedf_test_list
            for filtered_row in filtred_thedf_test_list:
                # Vérifiez si le nom de la variable correspond
                if variable_name in filtered_row:
                    # Mise à jour de la valeur dans df_min_max_top_15_list
                    row['value_from_filtr_thedf_test'] = filtered_row[variable_name]
                    # Sortez de la boucle interne si la correspondance est trouvée pour cette variable
                    break

        df_min_max_split = []
        for row in df_min_max_top_15_list:
            min_val_str, max_val_str = row['value'].split('-')
            # Supprimer les espaces blancs et convertir en float
            min_val = min_val_str.strip()
            max_val = max_val_str.strip()
            df_min_max_split.append({
                'variable': row['variable'],
                'min': min_val,
                'max': max_val,
            })

        for row in df_min_max_split:
            # Récupérez le nom de la variable dans df_min_max_top_15_list
            variable_name = row['variable']
            # Parcourez chaque dictionnaire dans filtred_thedf_test_list
            for filtered_row in filtred_thedf_test_list:
                # Vérifiez si le nom de la variable correspond
                if variable_name in filtered_row:
                    # Mise à jour de la valeur dans df_min_max_top_15_list
                    row['test_value'] = filtered_row[variable_name]
                    # Sortez de la boucle interne si la correspondance est trouvée pour cette variable
                    break

        # Extraire les données du premier élément de la liste
        data = filtred_thedf_test_list[0]

        # Créer un dictionnaire pour les champs et les valeurs
        indc_fields = [f'indc{i}' for i in range(1, 16)]
        value_fields = [f'value_indc{i}' for i in range(1, 16)]

        # Créer une instance de UrlPredected
        url_predicted_instance = UrlPredected(
            user=user_instance,
            Url=entered_url,
            Keyword=selected_keyword,
            date_test=datetime.now().date(),
            hour_test=datetime.now().time(),
            Top10=top10_value
        )

         # Ajouter les valeurs aux champs indc et value_indc
         # Ajouter les valeurs aux champs indc et value_indc
        for indc_field, value_field, (key, value) in zip(indc_fields, value_fields, data.items()):
            # Vérifiez si la valeur est vide ou nulle
            if value is None or value == '':
                print(f"Attention : La valeur pour {key} est vide, en cours d'assignation d'une valeur par défaut.")
                value = 0.0  # Assigner une valeur par défaut appropriée, ici 0.0

            # Assurez-vous que la valeur peut être convertie en float
            try:
                value = float(value)
            except ValueError as e:
                print(f"Erreur de conversion : {key} a une valeur non convertible en float : {value}")
                value = 0.0  # Assigner une valeur par défaut appropriée

            setattr(url_predicted_instance, indc_field, key)
            setattr(url_predicted_instance, value_field, value)

        # Sauvegarder l'instance dans la base de données
        url_predicted_instance.save()

        print("url_predicted_instance.Top10 :::::",url_predicted_instance.Top10 )
        
        # Créer les instances de MinMaxUrlValue associées
        for key, value in data.items():
            # Vérifiez si la valeur est vide ou nulle
            if value is None or value == '':
                print(f"Attention : La valeur pour {key} est vide, en cours d'assignation d'une valeur par défaut.")
                value = 0.0  # Assigner une valeur par défaut appropriée, ici 0.0

            # Assurez-vous que la valeur peut être convertie en float
            try:
                value = float(value)
            except ValueError as e:
                print(f"Erreur de conversion : {key} a une valeur non convertible en float : {value}")
                value = 0.0  # Assigner une valeur par défaut appropriée
            min_max_value = df_min_max[key].iloc[0] if key in df_min_max else ''
            # Si min_max_value est une chaîne vide, assignez une valeur par défaut
            if min_max_value == '':
                print(f"Attention : min_max_value pour {key} est vide, en cours d'assignation d'une valeur par défaut.")
                min_max_value = '0.0-0.0'

            min_max_value = df_min_max[key].iloc[0] if key in df_min_max else ''
            min_max_instance = MinMaxUrlValue(
                urlPredected_instance=url_predicted_instance,
                attribute_name=key,
                attribute_value=value,
                min_max=min_max_value
            )
            min_max_instance.save()

        # Convertir le DataFrame en une liste de dictionnaires
        df_importance_top_15_list = df_importance_top_15.to_dict(orient='records')
        df_importance_top_15_json = json.dumps(df_importance_top_15_list)
        df_min_max_split_json = json.dumps(df_min_max_split)

        print("j'affiche filtred_thedf_test_list",filtred_thedf_test_list)

        handle_result_url(selected_keyword, entered_url, user_instance, pred_res, df_min_max_top_15_list, filtred_thedf_test_list, df_importance_top_15_json, df_min_max_split_json)


def handle_result_url(keyword_entred, url_entred, user_instance, pred_res, df_min_max_top_15, filtred_thedf_test_list, df_importance_top_15_json, df_min_max_split_json):
    current_datetime = datetime.now()
    current_date = current_datetime.date()
    current_time = current_datetime.time()
    
    # Créer une instance de AnalysUrlResult
    analysis_result = AnalysUrlResult.objects.create(
        user=user_instance,
        keyword=keyword_entred,
        url=url_entred,
        pred_res=pred_res,
        df_min_max_top_15 = df_min_max_top_15,
        filtred_thedf_test_list = filtred_thedf_test_list,
        df_importance_top_15_json= df_importance_top_15_json,
        df_min_max_split_json = df_min_max_split_json,
        date_test=current_date,
        hour_test=current_time
    )

    # Enregistrer l'instance dans la base de données
    analysis_result.save()

    # Imprimer un message pour indiquer que l'enregistrement a réussi
    print("Analysis result successfully recorded")

    return pred_res, df_min_max_top_15, filtred_thedf_test_list, df_importance_top_15_json, df_min_max_split_json

def connect_and_consume():
    while True:
        try:
            # Connexion à RabbitMQ
            connection = pika.BlockingConnection(pika.ConnectionParameters(host='localhost', heartbeat=600, blocked_connection_timeout=300))
            channel = connection.channel()
            
            # Purger la file d'attente 'keyword_queue' avant de commencer à consommer
            channel.queue_declare(queue='keyword_queue')
            channel.queue_purge(queue='keyword_queue')
            print("Keyword Queue purged. Waiting for messages...")

            # Purger la file d'attente 'url_queue' avant de commencer à consommer
            channel.queue_declare(queue='url_queue')
            channel.queue_purge(queue='url_queue')
            print("URL Queue purged. Waiting for messages...")

            # Consommer les messages de 'keyword_queue' en utilisant process_message
            channel.basic_consume(queue='keyword_queue', on_message_callback=process_message)
            print(' [*] Waiting for messages from keyword_queue. To exit press CTRL+C')

            # Consommer les messages de 'url_queue' en utilisant process_message
            channel.basic_consume(queue='url_queue', on_message_callback=process_message)
            print(' [*] Waiting for messages from url_queue. To exit press CTRL+C')

            # Démarrer la consommation
            channel.start_consuming()
        
        except pika.exceptions.AMQPConnectionError as e:
            print(f"Connection error: {e}, retrying in 5 seconds...")
            time.sleep(5)
        
        except KeyboardInterrupt:
            print(" [*] Exiting due to user interrupt.")
            break
        
        except Exception as e:
            print(f"Unexpected error occurred: {e}")
            break

if __name__ == '__main__':
    connect_and_consume()

>>>>>>> 118a9726f6e6ad60be057cd63abf90561247e53c
