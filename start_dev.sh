python /tmp/app/local_login.py &

python -m uvicorn "backend:app" \
        --reload \
        --host="0.0.0.0" \
        --port=5463 \
        --timeout-keep-alive=60 \
        &

cp /tmp/app/nginx.conf /etc/nginx/conf.d
npm install
npm run dev &

nginx -g 'daemon off;'
