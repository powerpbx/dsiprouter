from flask import Blueprint, session, render_template,jsonify
from flask import Flask, render_template, request, redirect, abort, flash, session, url_for, send_from_directory
from sqlalchemy import case, func, exc as sql_exceptions
from werkzeug import exceptions as http_exceptions
from database import loadSession, Domain, DomainAttrs, dSIPDomainMapping, dSIPMultiDomainMapping, Dispatcher, Gateways, Subscribers, dSIPLeases, dSIPMaintModes
from shared import *
import  urllib.parse as parse
import json
import settings
import globals

db = loadSession()
api = Blueprint('api', __name__)

@api.route("/api/v1/kamailio/stats", methods=['GET'])
@api_security
def getKamailioStats():
    try:
        if (settings.DEBUG):
            debugEndpoint()

        payload = {"jsonrpc": "2.0", "method": "tm.stats","id": 1}
        #r = requests.get('https://www.google.com',data=payload)
        r = requests.get('http://127.0.0.1:5060/api/kamailio',json=payload)
        #print(r.text)

        return r.text

    except sql_exceptions.SQLAlchemyError as ex:
        debugException(ex, log_ex=False, print_ex=True, showstack=False)
        error = "db"
        db.rollback()
        db.flush()
        return showError(type=error)
    except http_exceptions.HTTPException as ex:
        debugException(ex, log_ex=False, print_ex=True, showstack=False)
        error = "http"
        db.rollback()
        db.flush()
        return showError(type=error)
    except Exception as ex:
        debugException(ex, log_ex=False, print_ex=True, showstack=False)
        error = "server"
        db.rollback()
        db.flush()
        return showError(type=error)
    finally:
        db.close()


@api.route("/api/v1/kamailio/reload", methods=['GET'])
@api_security
def reloadKamailio():
    try:
        if (settings.DEBUG):
            debugEndpoint()
        
        payloadResponse = {}
        configParameters = {}
        reloadCommands = {}
        #TODO: Get the configuration parameters to be updatable via the API
        #configParameters['cfg.sets:teleblock-gw_up'] = 'teleblock, gw_ip' + str(settings.TELEBLOCK_GW_IP)
        #configParameters['cfg.sets:teleblock-media_ip'] ='"teleblock", "media_ip",' +  str(settings.TELEBLOCK_MEDIA_IP)
        #configParameters['cfg.seti:teleblock-gw_enabled'] ='"teleblock", "gw_enabled",' +  str(settings.TELEBLOCK_GW_ENABLED)
        #configParameters['cfg.seti:teleblock-gw_port'] ='"teleblock", "gw_port",' +  str(settings.TELEBLOCK_GW_PORT)
        #configParameters['cfg.seti:teleblock-media_port'] ='"teleblock", "gw_media_port,' +  str(settings.TELEBLOCK_MEDIA_PORT)

        reloadCommands[0] = {"method": "permissions.addressReload", "jsonrpc": "2.0", "id": 1}
        reloadCommands[1] = {'method': 'drouting.reload', 'jsonrpc': '2.0', 'id': 1}
        reloadCommands[2] = {'method': 'domain.reload', 'jsonrpc': '2.0', 'id': 1}
        reloadCommands[3] = {'method': 'htable.reload', 'jsonrpc': '2.0', 'id': 1, 'params': ["maintmode"]}
        reloadCommands[4] = {'method': 'htable.reload', 'jsonrpc': '2.0', 'id': 1, 'params': ["tofromprefix"]}
        reloadCommands[5] = {'method': 'uac.reg_reload', 'jsonrpc': '2.0', 'id': 1}


        for element in reloadCommands:
            payload = reloadCommands[element]
            r = requests.get('http://127.0.0.1:5060/api/kamailio',json=payload)
            payloadResponse[payload['method']]=r.status_code



        #for key in configParameters:
        #    if "cfgs.sets" in key:
        #        payload = '{{"jsonrpc": "2.0", "method": "cfg.sets", "params" : [{}],"id": 1}}'.format(key,configParameters[key])
        #    elif "cfgi.seti" in key:
        #        payload = '{{"jsonrpc": "2.0", "method": "cfg.seti", "params" : {},"id": 1}}'.format(key,configParameters[key])
        #
        #    r = requests.get('http://127.0.0.1:5060/api/kamailio',json=payload)
        #   payloadResponse[key]=json.dumps({"status":r.status_code,"message":r.json()})
        #    payloadResponse[key]=r.status_code

        globals.reload_required = False 
        return json.dumps({"results": payloadResponse})

    except sql_exceptions.SQLAlchemyError as ex:
        debugException(ex, log_ex=False, print_ex=True, showstack=False)
        error = "db"
        db.rollback()
        db.flush()
        return showError(type=error)
    except http_exceptions.HTTPException as ex:
        debugException(ex, log_ex=False, print_ex=True, showstack=False)
        error = "http"
        db.rollback()
        db.flush()
        return showError(type=error)
    except Exception as ex:
        debugException(ex, log_ex=False, print_ex=True, showstack=False)
        error = "server"
        db.rollback()
        db.flush()
        return showError(type=error)
    finally:
        db.close()


@api.route("/api/v1/endpoint/lease", methods=['GET'])
@api_security
def getEndpointLease():
    try:
        if (settings.DEBUG):
            debugEndpoint()
        
        email=request.args.get('email')
        if not email:
            raise Exception("email parameter is missing")
        
        ttl=request.args.get('ttl')
        if not ttl:
            raise Exception("time to live (ttl) parameter is missing")

        # Generate some values
        rand_num= random.randint(1,200)
        name = "lease" + str(rand_num)
        auth_username = name
        auth_password = generatePassword()  
        auth_domain = settings.DOMAIN
        if settings.DSIP_API_HOST:
            api_hostname = settings.DSIP_API_HOST
        else:
            api_hostname = getExternalIP()

        #Set some defaults
        ip_addr =''
        strip=''
        prefix=''
        
        #Add the Gateways table

        Gateway = Gateways(name, ip_addr, strip, prefix, settings.FLT_PBX)
        db.add(Gateway)
        db.flush()

        #Add the Subscribers table

        Subscriber = Subscribers(auth_username, auth_password, auth_domain, Gateway.gwid, email)
        db.add(Subscriber)
        db.flush()

        #Add to the Leases table

        Lease = dSIPLeases(Gateway.gwid, Subscriber.id, int(ttl))
        db.add(Lease)
        db.flush()

        payload = {}
        payload['leaseid'] = Lease.id
        payload['username'] = auth_username
        payload['password'] = auth_password
        payload['hostname'] = api_hostname
        payload['domain'] = auth_domain
        payload['ttl'] = ttl

        #Commit transactions to database

        db.commit()
        return json.dumps(payload)

    except sql_exceptions.SQLAlchemyError as ex:
        debugException(ex, log_ex=False, print_ex=True, showstack=False)
        error = "db"
        #db.rollback()
        #db.flush()
        return showError(type=error)
    except http_exceptions.HTTPException as ex:
        debugException(ex, log_ex=False, print_ex=True, showstack=False)
        error = "http"
        #db.rollback()
        #db.flush()
        return showError(type=error)
    except Exception as ex:
        debugException(ex, log_ex=False, print_ex=True, showstack=False)
        error = "server"
        #db.rollback()
        #db.flush()
        return showError(type=error)
    finally:
        db.close()

@api.route("/api/v1/endpoint/lease/<int:leaseid>/revoke", methods=['PUT'])
@api_security
def revokeEndpointLease(leaseid):
    try:
        if (settings.DEBUG):
            debugEndpoint()
       
        # Query the Lease ID
        Lease = db.query(dSIPLeases).filter(dSIPLeases.id == leaseid).first()

        # Remove the entry in the Subscribers table
               
        Subscriber = db.query(Subscribers).filter(Subscribers.id == Lease.sid).first()
        db.delete(Subscriber)
        # Remove the entry in the Gateway table
        
        Gateway = db.query(Gateways).filter(Gateways.gwid == Lease.gwid).first()
        db.delete(Gateway)

        # Remove the entry in the Lease table
        
        db.delete(Lease)
        
        payload = {}
        payload['leaseid'] = leaseid
        payload['status'] = 'revoked'
        
        db.commit()
        return json.dumps(payload)

    except sql_exceptions.SQLAlchemyError as ex:
        debugException(ex, log_ex=False, print_ex=True, showstack=False)
        error = "db"
        db.rollback()
        db.flush()
        return showError(type=error)
    except http_exceptions.HTTPException as ex:
        debugException(ex, log_ex=False, print_ex=True, showstack=False)
        error = "http"
        db.rollback()
        db.flush()
        return showError(type=error)
    except Exception as ex:
        debugException(ex, log_ex=False, print_ex=True, showstack=False)
        error = "server"
        db.rollback()
        db.flush()
        return showError(type=error)
    finally:
        db.close()

class APIException(Exception):
    pass

class MaintModeAttrMissing(APIException):
    pass

@api.route("/api/v1/endpoint/<int:id>", methods=['POST'])
@api_security
def updateEndpoint(id):
    try:
        if (settings.DEBUG):
            debugEndpoint()
       
        # Define a dictionary object that represents the payload 
        responsePayload = {}
        
        # Set the status to 0, update it to 1 if the update is successful
        responsePayload['status'] = 0

        # Covert JSON message to Dictionary Object
        requestPayload = request.get_json()

        # Only handling the maintmode attribute on this release
        try:
             if 'maintmode' not in requestPayload:
                 raise MaintModeAttrMissing

             if requestPayload['maintmode'] == 0:
                 MaintMode = db.query(dSIPMaintModes).filter(dSIPMaintModes.gwid == id).first()
                 if MaintMode:
                     db.delete(MaintMode)
             elif requestPayload['maintmode'] == 1:
                #Lookup Gateway ip adddess
                 Gateway = db.query(Gateways).filter(Gateways.gwid == id).first()
                 db.commit()
                 db.flush()
                 if Gateway != None:
                     MaintMode = dSIPMaintModes(Gateway.address,id)
                 db.add(MaintMode)   
        except MaintModeAttrMissing as ex:
            responsePayload['error'] = "maintmode attribute is missing"
            return json.dumps(responsePayload)
        
        db.commit()
        responsePayload['status'] = 1

        return json.dumps(responsePayload)

    except sql_exceptions.SQLAlchemyError as ex:
        debugException(ex, log_ex=False, print_ex=True, showstack=False)
        error = "db"
        db.rollback()
        db.flush()
        if isinstance(ex, sql_exceptions.IntegrityError):
            responsePayload['error'] = "endpoint {} is already in maintmode".format(id)
        return json.dumps(responsePayload)
    except http_exceptions.HTTPException as ex:
        debugException(ex, log_ex=False, print_ex=True, showstack=False)
        error = "http"
        db.rollback()
        db.flush()
        return json.dumps(responsePayload)
    except Exception as ex:
        debugException(ex, log_ex=False, print_ex=True, showstack=False)
        error = "server"
        db.rollback()
        db.flush()
        return json.dumps(responsePayload)
    finally:
        db.close()
