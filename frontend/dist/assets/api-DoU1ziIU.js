function o(r,e={}){const t=localStorage.getItem("auth_token"),a={...e.headers||{}};return t&&(a.Authorization=`Bearer ${t}`),fetch(r,{...e,headers:a})}export{o as a};
