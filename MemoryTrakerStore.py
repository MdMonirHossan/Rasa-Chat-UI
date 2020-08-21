import contextlib
import json
import logging
import os
import pickle
import typing
import warnings
from datetime import datetime, timezone

from typing import Iterator, Optional, Text, Iterable, Union, Dict, Callable, List

import itertools
from boto3.dynamodb.conditions import Key

# noinspection PyPep8Naming
from time import sleep

from rasa.core import utils
from rasa.utils import common
from rasa.core.actions.action import ACTION_LISTEN_NAME

from rasa.core.events import SessionStarted


from rasa.core.brokers.broker import EventBroker

from rasa.core.conversation import Dialogue
from rasa.core.domain import Domain
from rasa.core.trackers import ActionExecuted, DialogueStateTracker, EventVerbosity
from rasa.utils.common import class_from_module_path
from rasa.utils.endpoints import EndpointConfig

if typing.TYPE_CHECKING:
    from sqlalchemy.engine.url import URL
    from sqlalchemy.engine.base import Engine
    from sqlalchemy.orm import Session
    import boto3.resources.factory.dynamodb.Table

logger = logging.getLogger(__name__)
from rasa.core.tracker_store import TrackerStore

# class MyTrackerStore(TrackerStore):
#     """
#     Stores conversation history in Mongo

#     Property methods:
#         conversations: returns the current conversation
#     """

#     def __init__(
#         self,
#         domain: Domain,
#         host: Optional[Text] = "mongodb://localhost:27017",
#         db: Optional[Text] = "rasa",
#         username: Optional[Text] = None,
#         password: Optional[Text] = None,
#         auth_source: Optional[Text] = "admin",
#         collection: Optional[Text] = "conversations",
#         event_broker: Optional[EventBroker] = None,
#     ):
#         from pymongo.database import Database
#         from pymongo import MongoClient

#         self.client = MongoClient(
#             host,
#             username=username,
#             password=password,
#             authSource=auth_source,
#             # delay connect until process forking is done
#             connect=False,
#         )

#         self.db = Database(self.client, db)
#         self.collection = collection
#         super().__init__(domain, event_broker)

#         self._ensure_indices()

#     @property
#     def conversations(self):
#         """Returns the current conversation"""
#         return self.db[self.collection]

#     def _ensure_indices(self):
#         """Create an index on the sender_id"""
#         self.conversations.create_index("sender_id")

#     # @staticmethod
#     # def _current_tracker_state_without_events(tracker: DialogueStateTracker) -> Dict:
#     #     # get current tracker state and remove `events` key from state
#     #     # since events are pushed separately in the `update_one()` operation
#     #     state = tracker.current_state(EventVerbosity.ALL)
#     #     state.pop("events", None)

#     #     return state

#     def save(self, tracker, timeout=None):
#         """Saves the current conversation state"""
#         if self.event_broker:
#             self.stream_events(tracker)

#         state = tracker.current_state(EventVerbosity.ALL)
#         serialised = MyTrackerStore.serialise_tracker(tracker)
#         # self.store[tracker.sender_id] = serialised
#         data = json.loads(serialised)
#         # print("Statattttdttdtdtdtdtdtdtdtdt", data)
#         events = data['events']
#         bot_reply = ""
#         user_intent = ""
#         chatbot_utter = ""
#         count = 0
#         for i in reversed(events):
#             count+=1
#             if i['event']=='bot':
#                 bot_reply = i['text']
#                 break
#         print("Bot reply",bot_reply)
#         for i in reversed(events):
#             count+=1
#             if i['event']=='user':
#                 # print(i)
#                 user_intent = i['parse_data']['intent']['name']
#                 date = i['timestamp']
#                 break
#         formate_time = datetime.fromtimestamp(date)
#         print("Date" , date)
#         count = 0
#         for i in reversed(events):
#             if i['event']=='action':
#                 count+=1
#                 if count==2:
#                     chatbot_utter = i['name']
#                     break
#         print("Utter " , chatbot_utter)
#         print("Latest Messagw", tracker.latest_message.text)
#         print("Sender Id", tracker.sender_id)
#         bot_data = {
#             "sender_id":tracker.sender_id, 
#             "sender_message":tracker.latest_message.text, 
#             "chatbot_message":bot_reply, 
#             "user_intent":user_intent, 
#             "chatbot_utter":chatbot_utter, 
#             "date":formate_time
#         }
#         self.conversations.update_one(
#             {"sender_id": tracker.sender_id},
#             {
#                 "$set": bot_data
#             },
#             upsert=True,
#         )

#     # def _additional_events(self, tracker: DialogueStateTracker) -> Iterator:
#     #     """Return events from the tracker which aren't currently stored.

#     #     Args:
#     #         tracker: Tracker to inspect.

#     #     Returns:
#     #         List of serialised events that aren't currently stored.

#     #     """

#     #     stored = self.conversations.find_one({"sender_id": tracker.sender_id})
#     #     n_events = len(stored.get("events", [])) if stored else 0

#     #     return itertools.islice(tracker.events, n_events, len(tracker.events))

#     # @staticmethod
#     # def _events_since_last_session_start(serialised_tracker: Dict) -> List[Dict]:
#     #     """Retrieve events since and including the latest `SessionStart` event.

#     #     Args:
#     #         serialised_tracker: Serialised tracker to inspect.

#     #     Returns:
#     #         List of serialised events since and including the latest `SessionStarted`
#     #         event. Returns all events if no such event is found.

#     #     """

#     #     events = []
#     #     for event in reversed(serialised_tracker.get("events", [])):
#     #         events.append(event)
#     #         if event["event"] == SessionStarted.type_name:
#     #             break

#     #     return list(reversed(events))

#     def retrieve(self, sender_id):
#         """
#         Args:
#             sender_id: the message owner ID

#         Returns:
#             `DialogueStateTracker`
#         """
#         stored = self.conversations.find_one({"sender_id": sender_id})

#         # look for conversations which have used an `int` sender_id in the past
#         # and update them.
#         if stored is None and sender_id.isdigit():
#             from pymongo import ReturnDocument

#             stored = self.conversations.find_one_and_update(
#                 {"sender_id": int(sender_id)},
#                 {"$set": {"sender_id": str(sender_id)}},
#                 return_document=ReturnDocument.AFTER,
#             )

#         if stored is not None:
#             if self.domain:
#                 max_event_history = 100
#             events = self._events_since_last_session_start(stored)
#             return DialogueStateTracker.from_dict(sender_id, stored.get("events"), self.domain.slots, max_event_history)
#         else:
#             logger.warnings(
#                 "Can't recreate tracker from mongo storage"
#                 "because no domain is set. Returning `None` instead."
#             )
#             return None

#     def keys(self) -> Iterable[Text]:
#         """Returns sender_ids of the Mongo Tracker Store"""
#         return [c["sender_id"] for c in self.conversations.find()]




# class SQLTrackerStore(TrackerStore):
#     """Store which can save and retrieve trackers from an SQL database."""

#     from sqlalchemy.ext.declarative import declarative_base

#     Base = declarative_base()

#     class SQLEvent(Base):
#         """Represents an event in the SQL Tracker Store"""

#         from sqlalchemy import Column, Integer, String, Float, Text

#         __tablename__ = "events"

#         id = Column(Integer, primary_key=True)
#         sender_id = Column(String(255), nullable=False, index=True)
#         type_name = Column(String(255), nullable=False)
#         timestamp = Column(String(255))
#         intent_name = Column(String(255))
#         action_name = Column(String(255))
#         data = Column(Text)

#     def __init__(
#         self,
#         domain: Optional[Domain] = None,
#         dialect: Text = "sqlite",
#         host: Optional[Text] = None,
#         port: Optional[int] = None,
#         db: Text = "rasa.db",
#         username: Text = None,
#         password: Text = None,
#         event_broker: Optional[EventBroker] = None,
#         login_db: Optional[Text] = None,
#         query: Optional[Dict] = None,
#     ) -> None:
#         from sqlalchemy.orm import sessionmaker
#         from sqlalchemy import create_engine
#         import sqlalchemy.exc

#         engine_url = self.get_db_url(
#             dialect, host, port, db, username, password, login_db, query
#         )
#         logger.debug(f"Attempting to connect to database via '{engine_url}'.")

#         # Database might take a while to come up
#         while True:
#             try:
#                 # pool_size and max_overflow can be set to control the number of
#                 # connections that are kept in the connection pool. Not available
#                 # for SQLite, and only  tested for postgresql. See
#                 # https://docs.sqlalchemy.org/en/13/core/pooling.html#sqlalchemy.pool.QueuePool
#                 if dialect == "postgresql":
#                     self.engine = create_engine(
#                         engine_url,
#                         pool_size=int(os.environ.get("SQL_POOL_SIZE", "50")),
#                         max_overflow=int(os.environ.get("SQL_MAX_OVERFLOW", "100")),
#                     )
#                 else:
#                     self.engine = create_engine(engine_url)

#                 # if `login_db` has been provided, use current channel with
#                 # that database to create working database `db`
#                 if login_db:
#                     self._create_database_and_update_engine(db, engine_url)

#                 try:
#                     self.Base.metadata.create_all(self.engine)
#                 except (
#                     sqlalchemy.exc.OperationalError,
#                     sqlalchemy.exc.ProgrammingError,
#                 ) as e:
#                     # Several Rasa services started in parallel may attempt to
#                     # create tables at the same time. That is okay so long as
#                     # the first services finishes the table creation.
#                     logger.error(f"Could not create tables: {e}")

#                 self.sessionmaker = sessionmaker(bind=self.engine)
#                 break
#             except (
#                 sqlalchemy.exc.OperationalError,
#                 sqlalchemy.exc.IntegrityError,
#             ) as error:

#                 logger.warning(error)
#                 sleep(5)

#         logger.debug(f"Connection to SQL database '{db}' successful.")

#         super().__init__(domain, event_broker)

#     @staticmethod
#     def get_db_url(
#         dialect: Text = "sqlite",
#         host: Optional[Text] = None,
#         port: Optional[int] = None,
#         db: Text = "rasa.db",
#         username: Text = None,
#         password: Text = None,
#         login_db: Optional[Text] = None,
#         query: Optional[Dict] = None,
#     ) -> Union[Text, "URL"]:
#         """Builds an SQLAlchemy `URL` object representing the parameters needed
#         to connect to an SQL database.

#         Args:
#             dialect: SQL database type.
#             host: Database network host.
#             port: Database network port.
#             db: Database name.
#             username: User name to use when connecting to the database.
#             password: Password for database user.
#             login_db: Alternative database name to which initially connect, and create
#                 the database specified by `db` (PostgreSQL only).
#             query: Dictionary of options to be passed to the dialect and/or the
#                 DBAPI upon connect.

#         Returns:
#             URL ready to be used with an SQLAlchemy `Engine` object.

#         """
#         from urllib.parse import urlsplit
#         from sqlalchemy.engine.url import URL

#         # Users might specify a url in the host
#         parsed = urlsplit(host or "")
#         if parsed.scheme:
#             return host

#         if host:
#             # add fake scheme to properly parse components
#             parsed = urlsplit("schema://" + host)

#             # users might include the port in the url
#             port = parsed.port or port
#             host = parsed.hostname or host

#         return URL(
#             dialect,
#             username,
#             password,
#             host,
#             port,
#             database=login_db if login_db else db,
#             query=query,
#         )

#     def _create_database_and_update_engine(self, db: Text, engine_url: "URL"):
#         """Create databse `db` and update engine to reflect the updated `engine_url`."""

#         from sqlalchemy import create_engine

#         self._create_database(self.engine, db)
#         engine_url.database = db
#         self.engine = create_engine(engine_url)

#     @staticmethod
#     def _create_database(engine: "Engine", db: Text):
#         """Create database `db` on `engine` if it does not exist."""

#         import psycopg2

#         conn = engine.connect()

#         cursor = conn.connection.cursor()
#         cursor.execute("COMMIT")
#         cursor.execute(f"SELECT 1 FROM pg_catalog.pg_database WHERE datname = '{db}'")
#         exists = cursor.fetchone()
#         if not exists:
#             try:
#                 cursor.execute(f"CREATE DATABASE {db}")
#             except psycopg2.IntegrityError as e:
#                 logger.error(f"Could not create database '{db}': {e}")

#         cursor.close()
#         conn.close()

#     @contextlib.contextmanager
#     def session_scope(self):
#         """Provide a transactional scope around a series of operations."""
#         session = self.sessionmaker()
#         try:
#             yield session
#         finally:
#             session.close()

#     def keys(self) -> Iterable[Text]:
#         """Returns sender_ids of the SQLTrackerStore"""
#         with self.session_scope() as session:
#             sender_ids = session.query(self.SQLEvent.sender_id).distinct().all()
#             return [sender_id for (sender_id,) in sender_ids]

#     def retrieve(self, sender_id: Text) -> Optional[DialogueStateTracker]:
#         """Create a tracker from all previously stored events."""

#         import sqlalchemy as sa
#         from rasa.core.events import SessionStarted

#         with self.session_scope() as session:
#             # Subquery to find the timestamp of the latest `SessionStarted` event
#             session_start_sub_query = (
#                 session.query(
#                     sa.func.max(self.SQLEvent.timestamp).label("session_start")
#                 )
#                 .filter(
#                     self.SQLEvent.sender_id == sender_id,
#                     self.SQLEvent.type_name == SessionStarted.type_name,
#                 )
#                 .subquery()
#             )

#             results = (
#                 session.query(self.SQLEvent)
#                 .filter(
#                     self.SQLEvent.sender_id == sender_id,
#                     # Find events after the latest `SessionStarted` event or return all
#                     # events
#                     sa.or_(
#                         self.SQLEvent.timestamp
#                         >= session_start_sub_query.c.session_start,
#                         session_start_sub_query.c.session_start.is_(None),
#                     ),
#                 )
#                 .order_by(self.SQLEvent.timestamp)
#                 .all()
#             )

#             events = [json.loads(event.data) for event in results]

#             if self.domain and len(events) > 0:
#                 logger.debug(f"Recreating tracker from sender id '{sender_id}'")
#                 return DialogueStateTracker.from_dict(
#                     sender_id, events, self.domain.slots
#                 )
#             else:
#                 logger.debug(
#                     f"Can't retrieve tracker matching "
#                     f"sender id '{sender_id}' from SQL storage. "
#                     f"Returning `None` instead."
#                 )
#                 return None

#     def save(self, tracker: DialogueStateTracker) -> None:
#         """Update database with events from the current conversation."""

#         if self.event_broker:
#             self.stream_events(tracker)
#         serialised = SQLTrackerStore.serialise_tracker(tracker)
#         # self.store[tracker.sender_id] = serialised
#         data1 = json.loads(serialised)
#         # print("Statattttdttdtdtdtdtdtdtdtdt", data)
#         events1 = data1['events']
#         bot_reply = ""
#         user_intent = ""
#         chatbot_utter = ""
#         count = 0
#         date = 0
#         for i in reversed(events1):
#             count+=1
#             if i['event']=='bot':
#                 bot_reply = i['text']
#                 break
#         print("Bot reply",bot_reply)
#         for i in reversed(events1):
#             count+=1
#             if i['event']=='user':
#                 # print(i)
#                 user_intent = i['parse_data']['intent']['name']
#                 date = i['timestamp']
#                 break
#         formate_time = datetime.fromtimestamp(date)
#         print("Date" , date)
#         count = 0
#         for i in reversed(events1):
#             if i['event']=='action':
#                 count+=1
#                 if count==2:
#                     chatbot_utter = i['name']
#                     break
#         print("Utter " , chatbot_utter)
#         print("Latest Messagw", tracker.latest_message.text)
#         print("Sender Id", tracker.sender_id)
#         with self.session_scope() as session:
#             # only store recent events
#             events = self._additional_events(session, tracker)

#             for event in events:
#                 data = event.as_dict()
#                 intent = data.get("parse_data", {}).get("intent", {}).get("name")
#                 action = data.get("name")
#                 timestamp = data.get("timestamp")
#                 session.add(
#                     self.SQLEvent(
#                         sender_id=tracker.sender_id,
#                         type_name=event.type_name,
#                         timestamp=timestamp,
#                         intent_name=intent,
#                         action_name=action,
#                         data=json.dumps(data),
#                     )
#                 )
#             session.commit()

#         logger.debug(f"Tracker with sender_id '{tracker.sender_id}' stored to database")

#     def _additional_events(
#         self, session: "Session", tracker: DialogueStateTracker
#     ) -> Iterator:
#         """Return events from the tracker which aren't currently stored."""

#         n_events = (
#             session.query(self.SQLEvent.sender_id)
#             .filter_by(sender_id=tracker.sender_id)
#             .count()
#             or 0
#         )

#         return itertools.islice(tracker.events, n_events, len(tracker.events))


class InMemoryTrackerStore(TrackerStore):
    """Stores conversation history in memory"""
    def __init__(
        self, 
        domain: Domain, 
        host="localhost",
        event_broker: Optional[EventBroker] = None
    ) -> None:
        self.store = {}
        super().__init__(domain, event_broker)

    def save(self, tracker: DialogueStateTracker) -> None:
        """Updates and saves the current conversation state"""
        if self.event_broker:
            self.stream_events(tracker)

        serialised = InMemoryTrackerStore.serialise_tracker(tracker)
        self.store[tracker.sender_id] = serialised

        data = json.loads(serialised)
        events = data['events']

        count=0
        reply = 4
        bot_reply=""
        user_intent = ""
        chatbot_utter = ""
        date = ""
        confidence = 0

        for i in reversed(events):
            count+=1
            if i['event']=='bot':
                bot_reply = i['text']
                break

        for i in reversed(events):
            count+=1
            if i['event']=='user':
                user_intent = i['parse_data']['intent']['name']
                confidence = i['parse_data']['intent']['confidence']
                date = i['timestamp']
                break
        print("Confidence", confidence)
        formate_time = datetime.fromtimestamp(date)
        count = 0
        for i in reversed(events):
            if i['event']=='action':
                count+=1
                if count==2:
                    chatbot_utter = i['name']
                    break
        
        # url = "https://agile-cove-96115.herokuapp.com/organization/botConversationCreate"

        datas = {
            "chatbot_id":11, 
            "sender_id":tracker.sender_id, 
            "sender_message":tracker.latest_message.text, 
            "chatbot_message":bot_reply, 
            "user_intent":user_intent, 
            "chatbot_utter":chatbot_utter, 
            "date":formate_time, 
            "confidence":confidence
            }
        # headers = {'Content-type': 'application/json'}
        # rsp = requests.post(url, json=datas, headers=headers)




        import pymongo
        from pymongo import MongoClient
        client = MongoClient('mongodb+srv://mdMonir:raju0183@chat-dat.aar0m.mongodb.net/Chat-dat?retryWrites=true&w=majority')
        database = client.conversation
        collection = database.data
        collection.insert_one(datas)

        print(datas)
        import csv  
    
        # field names  
        fields = ['Sender ID', 'Sender Message', 'Bot Reply', 'User Intent', 'Chatbot Utter', 'Date', 'confidence']  
            
        # data rows of csv file  
        rows = [ [tracker.sender_id, tracker.latest_message.text, bot_reply, user_intent, chatbot_utter, formate_time, confidence]]  
            
        # name of csv file  
        filename = "conversation.csv"
            
        # writing to csv file  
        with open(filename, 'a') as csvfile:  
            # creating a csv writer object  
            csvwriter = csv.writer(csvfile)  
                
            # writing the fields  
            # csvwriter.writerow(fields)  

            # data = [row for row in csv.reader(csvfile)]
            # print(data)

            # writing the data rows  
            csvwriter.writerows(rows)

    def retrieve(self, sender_id: Text) -> Optional[DialogueStateTracker]:
        """
        Args:
            sender_id: the message owner ID

        Returns:
            DialogueStateTracker
        """
        if sender_id in self.store:
            logger.debug(f"Recreating tracker for id '{sender_id}'")
            return self.deserialise_tracker(sender_id, self.store[sender_id])
        else:
            logger.debug(f"Creating a new tracker for id '{sender_id}'.")
            return None

    def keys(self) -> Iterable[Text]:
        """Returns sender_ids of the Tracker Store in memory"""
        return self.store.keys()