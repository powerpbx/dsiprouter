import psycopg2
import MySQLdb
import os
import subprocess
import docker
from database import Domain, DomainAttrs, dSIPMultiDomainMapping

#Obtain a set of FusionPBX systems that contains domains that Kamailio will route traffic to.
def get_sources(db):

    #Dictionary object to hold the set of source FusionPBX systems 
    sources = {}
    
    #Kamailio Database Parameters
    kam_hostname=db['hostname']
    kam_username=db['username']
    kam_password=db['password']
    kam_database=db['database']

    try:
        db=MySQLdb.connect(host=kam_hostname, user=kam_username, passwd=kam_password, db=kam_database)
        c=db.cursor()
        c.execute("""select pbx_id,address as pbx_host,db_host,db_username,db_password,domain_list,attr_list from dsip_multidomain_mapping join dr_gateways on dsip_multidomain_mapping.pbx_id=dr_gateways.gwid where enabled=1""")
        results =c.fetchall()
        db.close()
        for row in results:
            #Store the PBX_ID as the key and the entire row as the value
            sources[row[1]] =row
    except Exception as e:
        print(e)
   
    return sources

#Will remove all of the fusionpbx domain data so that it can be rebuilt
def drop_fusionpbx_domains(source, db):

    #PBX Domain Mapping Parameters
    pbx_domain_list=source[5]
    pbx_attr_list=source[6]

    #Kamailio Database Parameters
    kam_hostname=db['hostname']
    kam_username=db['username']
    kam_password=db['password']
    kam_database=db['database']

    pbx_domain_list = list(map(int, filter(None, pbx_domain_list.split(","))))
    pbx_attr_list = list(map(int, filter(None, pbx_attr_list.split(","))))

    try:
        db=MySQLdb.connect(host=kam_hostname, user=kam_username, passwd=kam_password, db=kam_database)
        c=db.cursor()

        if len(pbx_domain_list) > 0:
            c.execute("""DELETE FROM domain WHERE id IN({})""".format(pbx_domain_list))

        if len(pbx_attr_list > 0):
            c.execute("""DELETE FROM domain_attrs WHERE id IN({})""".format(pbx_attr_list))

        db.commit()
    except Exception as e:
        print(e)

def sync_db(source,dest):
   
    #FusionPBX Database Parameters 
    pbx_id =source[0]
    pbx_host =source[1]
    fpbx_hostname=source[2]
    fpbx_username=source[3]
    fpbx_password=source[4]
    pbx_domain_list=source[5]
    pbx_attr_list=source[6]
    fpbx_database = 'fusionpbx'

    #Kamailio Database Parameters
    kam_hostname=dest['hostname']
    kam_username=dest['username']
    kam_password=dest['password']
    kam_database=dest['database']
     
     
    domain_id_list = []
    attr_id_list = []

#Get a connection to Kamailio Server DB
    db=MySQLdb.connect(host=kam_hostname, user=kam_username, passwd=kam_password, db=kam_database)
    c=db.cursor()
    #Delete existing domain for the pbx
    pbx_domain_list_str = ''.join(str(e) for e in pbx_domain_list)
    print(pbx_domain_list_str)
    if len(pbx_domain_list_str) > 0:
        query = "delete from domain where id in ({})".format(pbx_domain_list_str)
        c.execute(query)
        pbx_domain_list=''
    


    #Trying connecting to PostgresSQL database using a Trust releationship first
    try:
        conn = psycopg2.connect(dbname=fpbx_database, user=fpbx_username, host=fpbx_hostname, password=fpbx_password)
        if conn is not None:
            print("Connection to FusionPBX:{} database was successful".format(fpbx_hostname))
        cur = conn.cursor()
        cur.execute("""select domain_name from v_domains where domain_enabled='true'""")
        rows = cur.fetchall()
        if rows is not None:
            c=db.cursor()
            counter = 0
            
            for row in rows:
                c.execute("""insert ignore into domain (id,domain,did,last_modified) values (null,%s,%s,NOW())""", (row[0],row[0]))
                print("row count {}".format(c.rowcount))
                if c.rowcount > 0:
                    c.execute("""SELECT AUTO_INCREMENT FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME IN('domain') ORDER BY FIND_IN_SET(TABLE_NAME, 'domain')""")
                    rows = c.fetchall()
                    domain_id_list.append(str(rows[0][0] -1))
                #Delete all domain_attrs for the domain first
                c.execute("""delete from domain_attrs where did=%s""", [row[0]])
                c.execute("""insert ignore into domain_attrs (id,did,name,type,value,last_modified) values (null,%s,'pbx_ip',2,%s,NOW())""", (row[0],pbx_host))
                c.execute("""insert ignore into domain_attrs (id,did,name,type,value,last_modified) values (null,%s,'pbx_type',2,%s,NOW())""", (row[0],dSIPMultiDomainMapping.FLAGS.TYPE_FUSIONPBX.value))
                c.execute("""insert ignore into domain_attrs (id,did,name,type,value,last_modified) values (null,%s,'created_by',2,%s,NOW())""", (row[0],pbx_id))
                c.execute("""insert ignore into domain_attrs (id,did,name,type,value,last_modified) values (null,%s,'domain_auth',2,%s,NOW())""", (row[0],'passthru'))
                c.execute("""insert ignore into domain_attrs (id,did,name,type,value,last_modified) values (null,%s,'pbx_list',2,%s,NOW())""", (row[0],pbx_id))
                c.execute("""insert ignore into domain_attrs (id,did,name,type,value,last_modified) values (null,%s,'description',2,%s,NOW())""", (row[0],'notes:'))
                counter = counter+1

            for i in domain_id_list:
                print(i)
            
            # Convert to a string seperated by commas
            domain_id_list = ','.join(domain_id_list)

            if not pbx_domain_list: #if empty string then this is the first set of domains
                pbx_domain_list = domain_id_list
            else:  #adding to an existing list of domains
                pbx_domain_list = pbx_domain_list + "," + domain_id_list

            


            c.execute("""update dsip_multidomain_mapping set domain_list=%s, syncstatus=1, lastsync=NOW(),syncerror='' where pbx_id=%s""",(pbx_domain_list,pbx_id))
            db.commit()                
    except Exception as e:
        c=db.cursor()
        c.execute("""update dsip_multidomain_mapping set syncstatus=0, lastsync=NOW(), syncerror=%s where pbx_id=%s""",(str(e),pbx_id))
        db.commit()
        #Remove lock file
        os.remove("./.sync-lock") 

        print(e)

def reloadkam(kamcmd_path):
       try:
          #subprocess.call(['kamcmd' ,'permissions.addressReload'])
          #subprocess.call(['kamcmd','drouting.reload'])
          subprocess.call([kamcmd_path,'domain.reload'])
          return True
       except:
           return False

def update_nginx(sources):

    print("Updating Nginx")
    
    #Connect to docker
    client = docker.from_env()
    if client is not None:
        print("Got handle to docker")

    try:
        
        # If there isn't any FusionPBX sources then just shutdown the container
        if len(sources) < 1:
            containers = client.containers.list()
            for container in containers:
                if container.name == "dsiprouter-nginx":
                    #Stop the container
                    container.stop()
                    container.remove(force=True)
                    print("Stopped nginx container")
            return
    except Exception as e:
        os.remove("./.sync-lock") 
        print(e)
    
    #Create the Nginx file

    serverList = ""
    for source in sources:
        serverList += "server " + str(source) + ":443;\n"

    #print(serverList)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    #print(script_dir)

    input = open(script_dir + "/dsiprouter.nginx.tpl")
    output = open(script_dir + "/dsiprouter.nginx","w")
    output.write(input.read().replace("##SERVERLIST##", serverList))
    output.close()
    input.close()


    #Check if dsiprouter-nginx is running. If so, reload nginx

    containers = client.containers.list()
    print("past container list")
    for container in containers:
        if container.name == "dsiprouter-nginx":
            #Execute a command to reload nginx
            container.exec_run("nginx -s reload")
            print("Reloaded nginx") 
            return

    #Start the container if one is not running
    try:
       print("trying to create a container")
       host_volume_path = script_dir + "/dsiprouter.nginx"
       html_volume_path = script_dir + "/html"
       #host_volume_path = script_dir
       print(host_volume_path)
       #remove the container with a name of dsiprouter-nginx to avoid conflicts if it already exists
       containerList=client.containers.list('dsiprouter-nginx')
       containerFound=False
       for c in containerList:
           if c.name == "dsiprouter-nginx":
               containerFound=True
       if containerFound:
           print("dsiprouter-nginx found...about to remove it and recreate")
           container=client.containers.get('dsiprouter-nginx')
           container.remove()
       client.containers.run(image='nginx:latest',
            name="dsiprouter-nginx",
            ports={'80/tcp':'80/tcp','443/tcp':'443/tcp'},
            volumes={
                host_volume_path: {'bind':'/etc/nginx/conf.d/default.conf','mode':'rw'},
                html_volume_path: {'bind':'/etc/nginx/html','mode':'rw'}
            },
            detach=True)
       print("created a container")
    except Exception as e:
        os.remove("./.sync-lock") 
        print(e)
                


def run_sync(settings):
    try: 
        #Set the system where sync'd data will be stored.  
        #The Kamailio DB in our case

        #If already running - don't run
        if os.path.isfile("./.sync-lock"):
            print("Already running")
            return

        else:
            f=open("./.sync-lock","w+")
            f.close()

        
        dest={}
        dest['hostname']=settings.KAM_DB_HOST
        dest['username']=settings.KAM_DB_USER
        dest['password']=settings.KAM_DB_PASS
        dest['database']=settings.KAM_DB_NAME

        #Get the list of FusionPBX's that needs to be sync'd
        sources = get_sources(dest)
        print(sources)
        #Remove all existing domain and domain_attrs entries
        #for key in sources:
        #    drop_fusionpbx_domains(sources[key], dest)
     
        #Loop thru each FusionPBX system and start the sync
        for key in sources:
            sync_db(sources[key],dest)
         
        #Reload Kamailio
        reloadkam(settings.KAM_KAMCMD_PATH)

        #Update Nginx configuration file for HTTP Provisioning and start docker container if we have FusionPBX systems
        #update_nginx(sources[key])
        if sources is not None and len(sources) > 0:
            sources = list(sources.keys())
            update_nginx(sources)
    except Exception as e:
        print(e)
    finally:
        #Remove lock file
        os.remove("./.sync-lock") 
