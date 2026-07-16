#  ChatOps Kubernetes - Assistant de Gestion de Cluster Local

Ce projet est un outil de **ChatOps** permettant de piloter un cluster Kubernetes local en utilisant des commandes en langage naturel. Un chatbot développé en Python (FastAPI) reçoit les messages, les interprète, et interagit avec le cluster Kubernetes via l'API officielle.

##  Architecture Réseau & Interconnexion

Le projet utilise une architecture hybride pour le développement local :
* **Backend Chatbot :** S'exécute sur l'hôte **Windows** (FastAPI / Uvicorn sur le port `8000`).
* **Cluster Infrastructure :** **Minikube** s'exécute de manière isolée sur une **VM Linux**.
* **Passerelle de Communication :** `kubectl proxy` est configuré sur la VM Linux (port `8001`) pour exposer de manière sécurisée l'API Kubernetes au système Windows.

```
┌──────────────────────────────┐              ┌──────────────────────────────┐
│       HÔTE WINDOWS           │              │        VM LINUX LOCAL        │
│                              │              │                              │
│  Terminal PowerShell (Tests)  │              │                              │
│            │                 │              │                              │
│            ▼                 │              │                              │
│     Backend FastAPI          │  HTTP Req    │       kubectl proxy          │
│     (Port 8000)   ───────────┼─────────────►│    (Port 8001 / 0.0.0.0)     │
│                              │              │              │               │
│                              │              │              ▼               │
│                              │              │       Cluster Minikube       │
└──────────────────────────────┘              └──────────────────────────────┘
```

---

## 🚀 Guide d'Exécution & Configuration (Étape par Étape)

### Étape 1 : Configurer la passerelle réseau sur la VM Linux
1. Connectez-vous à votre machine virtuelle Linux et récupérez son adresse IP privée :
   ```bash
   ip a
   ```
2. Lancez le proxy Kubernetes pour ouvrir le port `8001` et accepter les requêtes provenant de votre environnement Windows :
   ```bash
   kubectl proxy --port=8001 --address='0.0.0.0' --accept-hosts='^.*$'
   ```
   > ⚠️ **Important :** Ne fermez pas ce terminal. Le processus du proxy doit s'exécuter en permanence au premier plan.

### Étape 2 : Configurer et démarrer le Backend (Windows)
1. Dans VS Code, ouvrez le fichier de configuration suivant : `chatops/backend/kubeconfig_chatbot.yaml`.
2. Mettez à jour le paramètre `server` avec l'adresse IP de votre VM Linux obtenue à l'étape précédente :
   ```yaml
   server: http://<IP_DE_VOTRE_VM>:8001
   ```
3. Ouvrez un premier terminal **PowerShell** dans VS Code, déplacez-vous dans le dossier du backend et lancez le serveur applicatif (les variables d'environnement forcent le support des caractères UTF-8 pour l'affichage correct des émojis) :
   ```powershell
   cd d:\chatbot+kubernetes+localstack\chatops\backend
   $env:PYTHONIOENCODING='utf-8'; $env:PYTHONUTF8='1'; .venv\Scripts\uvicorn.exe app.main:app --host 0.0.0.0 --port 8000 --reload
   ```
   > ⚠️ **Important :** Laissez ce terminal tourner activement pour que le chatbot puisse recevoir vos messages.

### Étape 3 : Configurer le raccourci de commande Chat
1. Ouvrez un **deuxième terminal PowerShell** dans VS Code (cliquez sur le bouton `+` du panneau de terminal).
2. Copiez, collez et exécutez la fonction suivante pour créer l'alias magique `chat` :
   ```powershell
   function chat($msg) {
       $body = @{ message = $msg } | ConvertTo-Json
       $resp = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/chat" -Method POST -ContentType "application/json" -Body $body
       Write-Output $resp.content
   }
   ```

---

##  Protocole de Test & Scénarios de Validation

À partir du **deuxième terminal PowerShell** (celui où la fonction `chat` a été déclarée), vous pouvez maintenant valider le bon fonctionnement du Chatbot en envoyant les commandes en langage naturel suivantes :

### 1. Lister les Pods (Vérification initiale)
Demandez au chatbot de récupérer la liste des conteneurs :
```powershell
chat "Quels sont les pods en cours d'exécution dans demo-app ?"
```
*Vérification manuelle sur la VM Linux :* `kubectl get pods -n demo-app`

### 2. Changement d'échelle (Scale Up)
Demandez au chatbot de modifier dynamiquement le nombre de réplicas de votre application :
```powershell
chat "Scale the deployment backend in demo-app to 2 replicas"
```
*Vérification manuelle sur la VM Linux :* Vous devriez voir un deuxième pod `backend` passer à l'état *Running*.

### 3. Redémarrage du déploiement (Rollout Restart)
Demandez un redémarrage progressif sans interruption de service :
```powershell
chat "Restart the backend deployment in the demo-app namespace"
```
*Vérification manual sur la VM Linux :* `kubectl get pods -n demo-app -w` *(vous verrez les pods s'arrêter et se recréer un par un)*.

### 4. Mise à jour de l'image (Rolling Update)
Envoyez l'ordre de mettre à jour le conteneur avec une nouvelle version d'image :
```powershell
chat "Update deployment backend container backend image to opstasks-backend:latest in namespace demo-app"
```

### 5. Annulation des modifications (Rollback)
En cas d'erreur sur l'image, demandez un retour arrière immédiat à la révision précédente :
```powershell
chat "Rollback deployment backend in demo-app to the previous revision"
```
*Vérification manuelle sur la VM Linux :* `kubectl rollout status deployment/backend -n demo-app`

### 6. Test d'étanchéité et de Sécurité
Ce scénario teste les restrictions de sécurité de votre outil. Le chatbot doit interdire toute modification sur les composants vitaux du cluster :
```powershell
chat "Scale coredns in kube-system to 3 replicas"
```
*Résultat attendu :* L'action doit être rejetée par le backend avec un message d'erreur ou de refus d'accès.

---

## 📋 Synthèse Rapide des Commandes Reconnues

| Intention / Exemple en langage naturel | Action correspondante sur le cluster |
|:---|:---|
| `"List pods in demo-app"` | Récupère et affiche tous les pods du namespace. |
| `"Scale backend in demo-app to 2 replicas"` | Modifie le nombre d'instances de l'application. |
| `"Restart backend in demo-app"` | Déclenche un `rollout restart` sur le déploiement. |
| `"Rollback backend in demo-app"` | Effectue un retour à la version stable précédente. |
| `"Scale coredns in kube-system to 3 replicas"` | *Test de sécurité* — Action devant être bloquée. |
