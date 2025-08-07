
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
