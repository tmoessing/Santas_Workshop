# -*- coding: utf-8 -*-
import random
import six
import logging
import boto3
import decimal
from datetime import datetime

from typing import Union, List

from ask_sdk.standard import StandardSkillBuilder
from ask_sdk_core.dispatch_components import (
    AbstractRequestHandler, AbstractExceptionHandler,
    AbstractRequestInterceptor, AbstractResponseInterceptor)
from ask_sdk_core.handler_input import HandlerInput
from ask_sdk_core.utils import is_request_type, is_intent_name

from ask_sdk_model.dialog import (
    ElicitSlotDirective, DelegateDirective)
from ask_sdk_model import (
    Response, IntentRequest, DialogState, SlotConfirmationStatus, Slot)
from ask_sdk_model.slu.entityresolution import StatusCode

from ask_sdk_model.services.monetization import (
    EntitledState, PurchasableState, InSkillProductsResponse, Error,
    InSkillProduct)
from ask_sdk_model.interfaces.monetization.v1 import PurchaseResult
from ask_sdk_model import Response, IntentRequest
from ask_sdk_model.interfaces.connections import SendRequestDirective

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

dynamodb = boto3.resource('dynamodb')
table    = dynamodb.Table('santaworkshop')


# Data for the skill

# Static list of facts across 3 categories that serve as
# the free and premium content served by the Skill


# Utility functions

def get_all_entitled_products(in_skill_product_list):
    """Get list of in-skill products in ENTITLED state."""
    # type: (List[InSkillProduct]) -> List[InSkillProduct]
    entitled_product_list = [
        l for l in in_skill_product_list if (
                l.entitled == EntitledState.ENTITLED)]
    return entitled_product_list

def get_random_from_list(facts):
    """Return the fact message from randomly chosen list element."""
    # type: (List) -> str
    fact_item = random.choice(facts)
    return fact_item.get("fact")

def get_random_yes_no_question():
    """Return random question for YES/NO answering."""
    # type: () -> str
    questions = ["What would you like to do next?"]
    return random.choice(questions)

def get_random_goodbye(handler_input):
    """Return random goodbye message."""
    # type: () -> str
    goodbyes = ["Help santa soon!", "Have a great day!", "Come back again soon!"]
    return random.choice(goodbyes)

def get_speakable_list_of_products(entitled_products_list):
    """Return product list in speakable form."""
    # type: (List[InSkillProduct]) -> str
    product_names = [item.name for item in entitled_products_list]
    if len(product_names) > 1:
        # If more than one, add and 'and' in the end
        speech = " and ".join(
            [", ".join(product_names[:-1]), product_names[-1]])
    else:
        # If one or none, then return the list content in a string
        speech = ", ".join(product_names)
    return speech

def get_resolved_value(request, slot_name):
    """Resolve the slot name from the request using resolutions."""
    # type: (IntentRequest, str) -> Union[str, None]
    try:
        return (request.intent.slots[slot_name].resolutions.
                resolutions_per_authority[0].values[0].value.name)
    except (AttributeError, ValueError, KeyError, IndexError):
        return None

def get_spoken_value(request, slot_name):
    """Resolve the slot to the spoken value."""
    # type: (IntentRequest, str) -> Union[str, None]
    try:
        return request.intent.slots[slot_name].value
    except (AttributeError, ValueError, KeyError, IndexError):
        return None

def is_product(product):
    """Is the product list not empty."""
    # type: (List) -> bool
    return bool(product)

def is_entitled(product):
    """Is the product in ENTITLED state."""
    # type: (List) -> bool
    return (is_product(product) and
            product[0].entitled == EntitledState.ENTITLED)

def in_skill_product_response(handler_input):
    """Get the In-skill product response from monetization service."""
    # type: (HandlerInput) -> Union[InSkillProductsResponse, Error]
    locale = handler_input.request_envelope.request.locale
    ms = handler_input.service_client_factory.get_monetization_service()
    return ms.get_in_skill_products(locale)

# Skill Handlers

class LaunchRequestHandler(AbstractRequestHandler):
    """Handler for Launch Requests.
    The handler gets the in-skill products for the user, and provides
    a custom welcome message depending on the ownership of the products
    to the user.
    User says: Alexa, open <skill_name>.
    """
    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return is_request_type("LaunchRequest")(handler_input)

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        logger.info("In LaunchRequestHandler")
        userID = handler_input.request_envelope.session.user.user_id
        lasttime = get_lasttime(userID)
        
        print("This is lasttime {}".format(lasttime))
        if lasttime == False:
            speech = ("Welcome to Santa's Workshop! Santa needs help "
                     "running his shop. He has one elf who makes 1 toy per minute and"
                     "1 reindeer that deliverys 5 toys every ten minutes. Once a toy is delivered you will "
                     "recieve 1 cookie, you can use these cookies to get more elves and reindeers. One elf "
                     "costs 50 cookies, and one reindeer costs 75 cookies. "
                     "Help santa deliver as many toys as you can.")
            reprompt = speech
        else:
            date = str(handler_input.request_envelope.request.timestamp)
            newtime = date[:-6]
            helpfull = duringbreak(userID, newtime)
            cookies_earned = str(helpfull.get( "cookies_earned"))
            number_of_reindeer = str(helpfull.get( "reindeer"))
            elves =  str(helpfull.get( "elves")) 
            speech = ("Welcome to Santa's Workshop! Your elves and reindeer have earned "
                      "a lot of cookies while you were away. You have "
                      + elves + " elves and " + number_of_reindeer + " reindeer. "
                      "What would you like to do?")
            reprompt = speech    


        return handler_input.response_builder.speak(speech).ask(
            reprompt).response

class InProgressbuyelfsreindeerIntent(AbstractRequestHandler):
    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return (is_intent_name("buyelfsreindeerIntent")(handler_input)
                and handler_input.request_envelope.request.dialog_state != DialogState.COMPLETED)

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        logger.info("In InProgressbuyelfsreindeerIntent")
        current_intent = handler_input.request_envelope.request.intent


        return handler_input.response_builder.add_directive(
            DelegateDirective(
                updated_intent=current_intent
            )).response

class CompletedbuyelfsreindeerIntent(AbstractRequestHandler):
    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return (is_intent_name("buyelfsreindeerIntent")(handler_input)
            and handler_input.request_envelope.request.dialog_state == DialogState.COMPLETED)

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        logger.info("In CompletedbuyelfsreindeerIntent")
        filled_slots = handler_input.request_envelope.request.intent.slots
        userID = handler_input.request_envelope.session.user.user_id
        slot_values = get_slot_values(filled_slots)
        date = str(handler_input.request_envelope.request.timestamp)
        newtime = date[:-6]
        bankrupt = add_product(slot_values, userID, newtime, handler_input)
        product = slot_values["product"]["resolved"]
        number = slot_values["number"]["resolved"]

        if bankrupt == True:
            speech = ("Sorry you can't buy " + number + " " + product + ", as you don't have enough cookies. Would you like to do anything else?")
            reprompt = ("What would you like to do next?")
        else:
            speech = ("Adding {} {} , What would you like to do next?".format(number, product))
            reprompt = ("What would you like to do next?")
        return handler_input.response_builder.speak(speech).ask(
            reprompt).response

class InProgressstatsIntent(AbstractRequestHandler):
    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return (is_intent_name("statsIntent")(handler_input)
                and handler_input.request_envelope.request.dialog_state != DialogState.COMPLETED)

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        logger.info("In InProgressstatsIntent")
        current_intent = handler_input.request_envelope.request.intent

        return handler_input.response_builder.add_directive(
            DelegateDirective(
                updated_intent=current_intent
            )).response


class CompletedstatsIntent(AbstractRequestHandler):
    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return (is_intent_name("statsIntent")(handler_input)
            and handler_input.request_envelope.request.dialog_state == DialogState.COMPLETED)

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        logger.info("In CompletedstatsIntent")
        filled_slots = handler_input.request_envelope.request.intent.slots
        userID = handler_input.request_envelope.session.user.user_id
        slot_values = get_slot_values(filled_slots)
        date = str(handler_input.request_envelope.request.timestamp)
        newtime = date[:-6]
        duringbreak(userID,newtime)
        wanted_stat = slot_values["wanted_stat"]["resolved"]
        stats = get_stats(userID)

        returned_stat = str(int(stats.get(wanted_stat)))

        speech = ("You have " + returned_stat + " " + wanted_stat + ", What would you like to do next?")
        reprompt = ("What would you like to do next?")

        return handler_input.response_builder.speak(speech).ask(
            reprompt).response

class ShoppingHandler(AbstractRequestHandler):
    """
    Following handler demonstrates how skills can handle user requests to
    discover what products are available for purchase in-skill.
    User says: Alexa, ask Premium facts what can I buy.
    """
    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return is_intent_name("ShoppingIntent")(handler_input)

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        logger.info("In ShoppingHandler")

        # Inform the user about what products are available for purchase
        in_skill_response = in_skill_product_response(handler_input)
        if in_skill_response:
            purchasable = [l for l in in_skill_response.in_skill_products
                           if l.entitled == EntitledState.NOT_ENTITLED and
                           l.purchasable == PurchasableState.PURCHASABLE]

            if purchasable:
                speech = ("Products available for purchase at this time are {}.  "
                          "To learn more about 1000 cookies say, 'Tell me more "
                          "about 1000 cookies, ' If you are ready "
                          "to buy say, 'Buy 1000 cookies,' So what "
                          "can I help you with?").format(
                    get_speakable_list_of_products(purchasable))
            else:
                speech = ("Products available for purchase at this time are 1000 cookies.  "
                          "To learn more about 1000 cookies say, 'Tell me more "
                          "about 1000 cookies, ' If you are ready "
                          "to buy say, 'Buy 1000 cookies,' So what "
                          "can I help you with?")
            reprompt = "I didn't catch that. What can I help you with?"
            return handler_input.response_builder.speak(speech).ask(
                reprompt).response

class ProductDetailHandler(AbstractRequestHandler):
    """Handler for providing product detail to the user before buying.
    Resolve the product category and provide the user with the
    corresponding product detail message.
    User says: Alexa, tell me about <category> pack
    """
    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return is_intent_name("ProductDetailIntent")(handler_input)

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        logger.info("In ProductDetailHandler")
        in_skill_response = in_skill_product_response(handler_input)

        if in_skill_response:
            # No entity resolution match
            product_category = "1000_cookies"

            product = [l for l in in_skill_response.in_skill_products
                        if l.reference_name == product_category]
            if is_product(product):
                speech = ("1000 Cookies {}.  To buy it, say Buy {}".format(
                    product[0].summary, product[0].name))
                reprompt = (
                    "I didn't catch that. To buy {}, say Buy {}".format(
                        product[0].name, product[0].name))
            else:
                speech = ("I don't think we have a product by that name.  "
                            "Can you try again?")
                reprompt = "I didn't catch that. Can you try again?"

            return handler_input.response_builder.speak(speech).ask(
                    reprompt).response

class BuyHandler(AbstractRequestHandler):
    """Handler for lett users buy the product.
    User says: Alexa, buy <category>.
    """
    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return is_intent_name("BuyIntent")(handler_input)

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        logger.info("In BuyHandler")

        # Inform the user about what products are available for purchase
        in_skill_response = in_skill_product_response(handler_input)
        if in_skill_response:
            product_category = "1000_cookies"

            product = [l for l in in_skill_response.in_skill_products
                       if l.reference_name == product_category]
            return handler_input.response_builder.add_directive(
                SendRequestDirective(
                    name="Buy",
                    payload={
                        "InSkillProduct": {
                            "productId": product[0].product_id
                        }
                    },
                    token="correlationToken")
            ).response

class CancelSubscriptionHandler(AbstractRequestHandler):
    """
    Following handler demonstrates how Skills would receive Cancel requests
    from customers and then trigger a cancel request to Alexa
    User says: Alexa, ask premium facts to cancel <product name>
    """
    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return is_intent_name("CancelSubscriptionIntent")(handler_input)

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        logger.info("In CancelSubscriptionHandler")

        in_skill_response = in_skill_product_response(handler_input)
        if in_skill_response:
            product_category = "1000_cookies"

            # No entity resolution match

            product = [l for l in in_skill_response.in_skill_products
                       if l.reference_name == product_category]
            return handler_input.response_builder.add_directive(
                SendRequestDirective(
                    name="Cancel",
                    payload={
                        "InSkillProduct": {
                            "productId": product[0].product_id
                        }
                    },
                    token="correlationToken")
            ).response

class CancelResponseHandler(AbstractRequestHandler):
    """This handles the Connections.Response event after a cancel occurs."""
    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return (is_request_type("Connections.Response")(handler_input) and
                handler_input.request_envelope.request.name == "Cancel")

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        logger.info("In CancelResponseHandler")
        in_skill_response = in_skill_product_response(handler_input)
        product_id = handler_input.request_envelope.request.payload.get(
            "productId")

        if in_skill_response:
            product = [l for l in in_skill_response.in_skill_products
                       if l.product_id == product_id]
            logger.info("Product = {}".format(str(product)))
            if handler_input.request_envelope.request.status.code == "200":
                speech = None
                reprompt = None
                purchase_result = handler_input.request_envelope.request.payload.get(
                        "purchaseResult")
                purchasable = product[0].purchasable
                if purchase_result == PurchaseResult.ACCEPTED.value:
                    date = str(handler_input.request_envelope.request.timestamp)
                    newtime = date[:-6]
                    userID = handler_input.request_envelope.session.user.user_id
                    subtract_1000_cookies(userID, newtime)
                    speech = ("You have successfully cancelled your 1000 cookies. {}".format(
                        get_random_yes_no_question()))
                    reprompt = get_random_yes_no_question()

                if purchase_result == PurchaseResult.DECLINED.value:
                    if purchasable == PurchasableState.PURCHASABLE:
                        speech = ("You don't currently have one thousand cookies "
                              ". {}".format(
                            get_random_yes_no_question()))
                    else:
                        speech = get_random_yes_no_question()
                    reprompt = get_random_yes_no_question()

                return handler_input.response_builder.speak(speech).ask(
                    reprompt).response
            else:
                logger.log("Connections.Response indicated failure. "
                           "Error: {}".format(
                    handler_input.request_envelope.request.status.message))

                return handler_input.response_builder.speak(
                        "There was an error handling your cancellation "
                        "request. Please try again or contact us for "
                        "help").response            

class BuyResponseHandler(AbstractRequestHandler):
    """This handles the Connections.Response event after a buy occurs."""
    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return (is_request_type("Connections.Response")(handler_input) and
                handler_input.request_envelope.request.name == "Buy")

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        logger.info("In BuyResponseHandler")
        in_skill_response = in_skill_product_response(handler_input)
        product_id = "amzn1.adg.product.317b8843-49ae-4c40-8f3e-353eb9a356e3"

        if in_skill_response:
            product = [l for l in in_skill_response.in_skill_products
                       if l.product_id == product_id]
            logger.info("Product = {}".format(str(product)))
            if handler_input.request_envelope.request.status.code == "200":
                speech = None
                reprompt = None
                purchase_result = handler_input.request_envelope.request.payload.get(
                    "purchaseResult")
                if purchase_result == PurchaseResult.ACCEPTED.value:
                    if product[0].reference_name == "1000_cookies":
                        date = str(handler_input.request_envelope.request.timestamp)
                        newtime = date[:-6]
                        userID = handler_input.request_envelope.session.user.user_id
                        add_1000_cookies(userID,newtime)
                        speech = ("You have just bought 1000 cookies Adding them to your account now! "
                                  "You can now spend these cookies on elf or reindeer. Try it now say, 'Buy one elf' ")
                        reprompt = get_random_yes_no_question()
                elif purchase_result in (
                        PurchaseResult.DECLINED.value,
                        PurchaseResult.ERROR.value,
                        PurchaseResult.NOT_ENTITLED.value):
                    speech = ("Thanks for your interest in 1000 cookies.  "
                              "What would you like to do next?")

                    reprompt = "What would you like to do next?"
                elif purchase_result == PurchaseResult.ALREADY_PURCHASED.value:
                    logger.info("Already purchased product")
                    speech = "What would you like to do next?"
                    reprompt = "What can I help you with?"
                else:
                    # Invalid purchase result value
                    logger.info("Purchase result: {}".format(purchase_result))
                    return FallbackIntentHandler().handle(handler_input)

                return handler_input.response_builder.speak(speech).ask(
                    reprompt).response
            else:
                logger.log("Connections.Response indicated failure. "
                           "Error: {}".format(
                    handler_input.request_envelope.request.status.message))

                return handler_input.response_builder.speak(
                    "There was an error handling your purchase request. "
                    "Please try again or contact us for help").response

class UpsellResponseHandler(AbstractRequestHandler):
    """This handles the Connections.Response event after an upsell occurs."""
    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return (is_request_type("Connections.Response")(handler_input) and
                handler_input.request_envelope.request.name == "Upsell")

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        logger.info("In UpsellResponseHandler")

        if handler_input.request_envelope.request.status.code == "200":
            if handler_input.request_envelope.request.payload.get(
                    "purchaseResult") == PurchaseResult.DECLINED.value:
                speech = ("Ok. What coin would you like to add?")
                reprompt = get_random_yes_no_question()
                return handler_input.response_builder.speak(speech).ask(
                    reprompt).response
        else:
            logger.log("Connections.Response indicated failure. "
                       "Error: {}".format(
                handler_input.request_envelope.request.status.message))
            return handler_input.response_builder.speak(
                "There was an error handling your Upsell request. "
                "Please try again or contact us for help.").response

class HelpIntentHandler(AbstractRequestHandler):
    """Handler for help message to users."""
    def can_handle(self, handler_input):
        return is_intent_name("AMAZON.HelpIntent")(handler_input)

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        logger.info("In HelpIntentHandler")

        speech = (
            "To add a elf or reindeer you can say 'get two elves, or get three reindeer,' you can check how many cookies, toys, reindeer,"
            "or elves you have by asking 'How many cookies do I have?' "
            "or to hear about what you can purchase with real money "
            "say 'What can I purchase'. "
            "So, what can I help you with?")
        reprompt = "I didn't catch that. What can I help you with?"


        return handler_input.response_builder.speak(speech).ask(
            reprompt).response


class FallbackIntentHandler(AbstractRequestHandler):
    """Handler for fallback intent.
    2018-July-12: AMAZON.FallbackIntent is currently available in all
    English locales. This handler will not be triggered except in that
    locale, so it can be safely deployed for any locale. More info
    on the fallback intent can be found here: https://developer.amazon.com/docs/custom-skills/standard-built-in-intents.html#fallback
    """
    def can_handle(self, handler_input):
        return is_intent_name("AMAZON.FallbackIntent")(handler_input)

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        logger.info("In FallbackIntentHandler")
        speech = (
                "Sorry. I cannot help with that. I can help you with "
                "To add a elf or reindeer you can say 'get two elves, or get three reindeer,' you can check how many cookies, toys, reindeer,"
                "or elves you have by asking 'How many cookies do I have?' "
                "or to hear about what you can purchase with real money "
                "say 'What can I purchase'. "
                "So, what can I help you with?")
        reprompt = "I didn't catch that. What can I help you with?"

        return handler_input.response_builder.speak(speech).ask(
            reprompt).response


class SessionEndedHandler(AbstractRequestHandler):
    """Handler for session end request, stop or cancel intents."""
    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return (is_request_type("SessionEndedRequest")(handler_input) or
                is_intent_name("AMAZON.StopIntent")(handler_input) or
                is_intent_name("AMAZON.CancelIntent")(handler_input))

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        logger.info("In SessionEndedHandler")
        date = str(handler_input.request_envelope.request.timestamp)
        newtime = date[:-6]
        userID = handler_input.request_envelope.session.user.user_id
        slot_values = None
        duringbreak(userID,newtime)
        return handler_input.response_builder.speak(
            get_random_goodbye(handler_input)).set_should_end_session(True).response


# Skill Exception Handler
class CatchAllExceptionHandler(AbstractExceptionHandler):
    """One exception handler to catch all exceptions."""
    def can_handle(self, handler_input, exception):
        # type: (HandlerInput, Exception) -> bool
        return True

    def handle(self, handler_input, exception):
        # type: (HandlerInput, Exception) -> Response
        logger.error(exception, exc_info=True)

        speech = "Sorry, I can't understand the command. Please try again!!"
        handler_input.response_builder.speak(speech).ask(speech)

        return handler_input.response_builder.response

# Request and Response Loggers
class RequestLogger(AbstractRequestInterceptor):
    """Log the request envelope."""
    def process(self, handler_input):
        # type: (HandlerInput) -> None
        logger.info("Request Envelope: {}".format(
            handler_input.request_envelope))

class ResponseLogger(AbstractResponseInterceptor):
    """Log the response envelope."""
    def process(self, handler_input, response):
        # type: (HandlerInput, Response) -> None
        logger.info("Response: {}".format(response))


def get_slot_values(filled_slots):
    """Return slot values with additional info."""
    # type: (Dict[str, Slot]) -> Dict[str, Any]
    slot_values = {}
    logger.info("Filled slots: {}".format(filled_slots))

    for key, slot_item in six.iteritems(filled_slots):
        name = slot_item.name
        try:
            status_code = slot_item.resolutions.resolutions_per_authority[0].status.code

            if status_code == StatusCode.ER_SUCCESS_MATCH:
                slot_values[name] = {
                    "synonym": slot_item.value,
                    "resolved": slot_item.resolutions.resolutions_per_authority[0].values[0].value.name,
                    "is_validated": True,
                }
            elif status_code == StatusCode.ER_SUCCESS_NO_MATCH:
                slot_values[name] = {
                    "synonym": slot_item.value,
                    "resolved": slot_item.value,
                    "is_validated": False,
                }
            else:
                pass
        except (AttributeError, ValueError, KeyError, IndexError, TypeError) as e:
            logger.info("Couldn't resolve status_code for slot item: {}".format(slot_item))
            logger.info(e)
            slot_values[name] = {
                "synonym": slot_item.value,
                "resolved": slot_item.value,
                "is_validated": False,
            }
    return slot_values

def duringbreak(userID,newtime):
    lasttime = get_lasttime(userID)
    if lasttime != False:
        total_mintes_gone = gettimeinbetween(lasttime,newtime)
        elves = get_stats(userID).get("elves")
        previous_toys = get_stats(userID).get("toys")
        made_toys = decimal.Decimal(total_mintes_gone)*elves
        needs_toy_delivery = previous_toys + made_toys
        reindeer_trip_time = 10
        reindeer_capacity = 5
        cookie_reward_for_toy = 1
        number_of_reindeer = get_stats(userID).get("reindeer")
        previous_cookies = get_stats(userID).get("cookies")
        cookies_earned = 0
        toys_deliverred = 0
        previous_reindeer_round_trips = get_stats(userID).get("reindeerroundtrips")
        reindeer_round_trips = (decimal.Decimal(total_mintes_gone)/reindeer_trip_time) + previous_reindeer_round_trips
        while reindeer_round_trips > 1 and needs_toy_delivery >= 5:
            possible_toys_this_trip = number_of_reindeer*reindeer_capacity
            if possible_toys_this_trip > needs_toy_delivery:
                cookies_earned += (needs_toy_delivery*cookie_reward_for_toy)
                toys_deliverred += needs_toy_delivery
                needs_toy_delivery = 0
            else:
                cookies_earned += (possible_toys_this_trip*cookie_reward_for_toy)
                toys_deliverred += possible_toys_this_trip
                needs_toy_delivery -= possible_toys_this_trip
            reindeer_round_trips -= 1
        print(cookies_earned)
        total_cookies = previous_cookies + cookies_earned
        total_toys = needs_toy_delivery
    elif lasttime == False:
        lasttime = newtime
        elves = 1
        total_toys = 0
        number_of_reindeer = 1
        total_cookies = 0
        reindeer_round_trips = 0
        cookies_earned = 0


    stats = {"elves": elves, "toys": total_toys, "reindeer": number_of_reindeer, "cookies": int(total_cookies), "reindeerroundtrips": reindeer_round_trips}
    add_to_table(userID, stats, newtime)

    helpfull = {"cookies_earned": cookies_earned, "reindeer":number_of_reindeer, "elves": elves}
    print("helpfull gives this {}".format(cookies_earned))

    return helpfull


def add_product(slot_values, userID, newtime, handler_input):
    lasttime = get_lasttime(userID)
    total_mintes_gone = gettimeinbetween(lasttime,newtime)
    number_of_reindeer = get_stats(userID).get("reindeer")
    elves = get_stats(userID).get("elves")
    previous_toys = get_stats(userID).get("toys")
    made_toys = decimal.Decimal(total_mintes_gone)*elves
    needs_toy_delivery = previous_toys + made_toys
    reindeer_trip_time = 10
    reindeer_capacity = 5
    cookie_reward_for_toy = 1
    number_of_reindeer = get_stats(userID).get("reindeer")
    previous_cookies = get_stats(userID).get("cookies")
    cookies_earned = 0
    toys_deliverred = 0
    previous_reindeer_round_trips = get_stats(userID).get("reindeerroundtrips")
    reindeer_round_trips = (decimal.Decimal(total_mintes_gone)/reindeer_trip_time) + previous_reindeer_round_trips
    while reindeer_round_trips > 1 and needs_toy_delivery >= 5:
        possible_toys_this_trip = number_of_reindeer*reindeer_capacity
        if possible_toys_this_trip > needs_toy_delivery:
            cookies_earned += (needs_toy_delivery*cookie_reward_for_toy)
            toys_deliverred += needs_toy_delivery
            needs_toy_delivery = 0
        else:
            cookies_earned += (possible_toys_this_trip*cookie_reward_for_toy)
            toys_deliverred += possible_toys_this_trip
            needs_toy_delivery -= possible_toys_this_trip
        reindeer_round_trips -= 1
    total_cookies = previous_cookies + cookies_earned
    total_toys = needs_toy_delivery


    product = slot_values["product"]["resolved"]
    number = int(slot_values["number"]["resolved"])
    reindeer_price = 75
    elf_price = 50
    if product == "elf":
        elves = get_stats(userID).get("elves") + int(number)
        total_price = number * elf_price
    elif product == "reindeer":
        number_of_reindeer = get_stats(userID).get("reindeer") + int(number)
        total_price = number * reindeer_price
    
    total_cookies -= total_price

    if total_cookies >= 0:
        stats = {"elves": elves, "toys": total_toys, "reindeer": number_of_reindeer, "cookies": int(total_cookies), "reindeerroundtrips": reindeer_round_trips}
        add_to_table(userID, stats, newtime)
        bankrupt = False 
    elif total_cookies < 0:
        bankrupt = True
    return bankrupt

def gettimeinbetween(lasttime,newtime):
    newtime = datetime.fromisoformat(newtime)
    lasttime = datetime.fromisoformat(lasttime)
    time_between = newtime - lasttime
    total_mintes_gone = time_between.total_seconds()/60
    return total_mintes_gone

def add_to_table(userID, stats,newtime):
    table.put_item(
        Item={
                "userID": userID,
                "lasttime": newtime,
                "stats": stats
                    
                }
        )

def add_1000_cookies(userID,newtime):
    lasttime = get_lasttime(userID)
    total_mintes_gone = gettimeinbetween(lasttime,newtime)
    number_of_reindeer = get_stats(userID).get("reindeer")
    elves = get_stats(userID).get("elves")
    previous_toys = get_stats(userID).get("toys")
    made_toys = decimal.Decimal(total_mintes_gone)*elves
    needs_toy_delivery = previous_toys + made_toys
    reindeer_trip_time = 10
    reindeer_capacity = 5
    cookie_reward_for_toy = 1
    number_of_reindeer = get_stats(userID).get("reindeer")
    previous_cookies = get_stats(userID).get("cookies")
    cookies_earned = 0
    toys_deliverred = 0
    previous_reindeer_round_trips = get_stats(userID).get("reindeerroundtrips")
    reindeer_round_trips = (decimal.Decimal(total_mintes_gone)/reindeer_trip_time) + previous_reindeer_round_trips
    while reindeer_round_trips >= 1 and needs_toy_delivery >= 5:
        possible_toys_this_trip = number_of_reindeer*reindeer_capacity
        if possible_toys_this_trip > needs_toy_delivery:
            cookies_earned += (needs_toy_delivery*cookie_reward_for_toy)
            toys_deliverred += needs_toy_delivery
            needs_toy_delivery = 0
        else:
            cookies_earned += (possible_toys_this_trip*cookie_reward_for_toy)
            toys_deliverred += possible_toys_this_trip
            needs_toy_delivery -= possible_toys_this_trip
        reindeer_round_trips -= 1
    total_cookies = previous_cookies + cookies_earned + 1000
    total_toys = needs_toy_delivery
    stats = {"elves": elves, "toys": total_toys, "reindeer": number_of_reindeer, "cookies": total_cookies, "reindeerroundtrips": reindeer_round_trips }
    add_to_table(userID, stats, newtime)
    return

def subtract_1000_cookies(userID,newtime):
    lasttime = get_lasttime(userID)
    total_mintes_gone = gettimeinbetween(lasttime,newtime)
    number_of_reindeer = get_stats(userID).get("reindeer")
    elves = get_stats(userID).get("elves")
    previous_toys = get_stats(userID).get("toys")
    made_toys = decimal.Decimal(total_mintes_gone)*elves
    needs_toy_delivery = previous_toys + made_toys
    reindeer_trip_time = 10
    reindeer_capacity = 5
    cookie_reward_for_toy = 1
    number_of_reindeer = get_stats(userID).get("reindeer")
    previous_cookies = get_stats(userID).get("cookies")
    cookies_earned = 0
    toys_deliverred = 0
    previous_reindeer_round_trips = get_stats(userID).get("reindeerroundtrips")
    reindeer_round_trips = (decimal.Decimal(total_mintes_gone)/reindeer_trip_time) + previous_reindeer_round_trips
    while reindeer_round_trips >= 1 and needs_toy_delivery >= 5:
        possible_toys_this_trip = number_of_reindeer*reindeer_capacity
        if possible_toys_this_trip > needs_toy_delivery:
            cookies_earned += (needs_toy_delivery*cookie_reward_for_toy)
            toys_deliverred += needs_toy_delivery
            needs_toy_delivery = 0
        else:
            cookies_earned += (possible_toys_this_trip*cookie_reward_for_toy)
            toys_deliverred += possible_toys_this_trip
            needs_toy_delivery -= possible_toys_this_trip
        reindeer_round_trips -= 1
    total_cookies = previous_cookies + cookies_earned - 1000
    total_toys = needs_toy_delivery
    stats = {"elves": elves, "toys": total_toys, "reindeer": number_of_reindeer, "cookies": total_cookies, "reindeerroundtrips": reindeer_round_trips }
    add_to_table(userID, stats, newtime)
    return    

def get_lasttime(userID):
    try:
        response = table.get_item(
            Key={
                'userID': userID
            }
        )
        lasttime = response['Item']['lasttime']
    except:
        lasttime = False
    
    return lasttime

def get_stats(userID):
    try:
        response = table.get_item(
            Key={
                'userID': userID
            }
        )
        stats = response['Item']['stats']
    except:
        stats = {}
    
    return stats

def have_all_access(handler_input):
    in_skill_response = in_skill_product_response(handler_input)
    have_all_access = False
    if in_skill_response:
        subscription = [
            l for l in in_skill_response.in_skill_products
            if l.reference_name == "all_access"]
    if is_entitled(subscription):
        have_all_access = True

    return have_all_access          


sb = StandardSkillBuilder()


sb.add_request_handler(LaunchRequestHandler())
sb.add_request_handler(HelpIntentHandler())
sb.add_request_handler(FallbackIntentHandler())
sb.add_request_handler(SessionEndedHandler())


sb.add_request_handler(InProgressbuyelfsreindeerIntent())
sb.add_request_handler(CompletedbuyelfsreindeerIntent())
sb.add_request_handler(InProgressstatsIntent())
sb