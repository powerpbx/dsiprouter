    upstream fusionpbx {
	##SERVERLIST##  
  }


    server {
        listen 80;
        listen 443 ssl;

        ssl_certificate         /etc/nginx/html/certs/cert_combined.crt;
        ssl_certificate_key     /etc/nginx/html/certs/cert.key;

        location /provision/ {
            proxy_pass https://fusionpbx;
            proxy_redirect off;
	    proxy_next_upstream error timeout http_404 http_403 http_500 http_502 http_503 http_504 non_idempotent;
        }

	location / {
	
	error_page 404	/404.html;

	}

	location /images/ {

	    alias /etc/nginx/html/images/;
	}
	
    }
