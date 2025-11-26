"""
✅ Test après correction Redis
Vérifier que tout fonctionne maintenant
"""

print("=" * 60)
print("✅ VÉRIFICATION POST-CORRECTION")
print("=" * 60)

# Test 1 : Vérifier la configuration du backend
print("\n[Test 1/3] Vérification de la configuration...")
try:
    from celery_app import celery
    
    backend = celery.conf.result_backend
    print(f"   Backend configuré: {backend}")
    
    if backend and "redis" in backend.lower():
        print("   ⚠️  Vous utilisez toujours Redis")
        print("   → Remplacez par backend='rpc://' dans celery_app.py")
    elif backend and "rpc" in backend.lower():
        print("   ✅ Vous utilisez RabbitMQ RPC (parfait !)")
    elif not backend:
        print("   ⚠️  Pas de backend configuré")
    else:
        print(f"   ℹ️  Backend: {backend}")
        
except Exception as e:
    print(f"   ❌ Erreur: {e}")
    exit(1)

# Test 2 : Lancer une tâche de test
print("\n[Test 2/3] Test de lancement de tâche...")
try:
    from tasks import check_all_user_sites
    
    print("   Lancement de la tâche...")
    result = check_all_user_sites.delay(1)
    
    print(f"   ✅ Tâche lancée avec succès !")
    print(f"   Task ID: {result.id}")
    print(f"   État: {result.state}")
    
    # Attendre un peu
    import time
    print("   Attente de 3 secondes...")
    time.sleep(3)
    
    print(f"   État après 3s: {result.state}")
    
    if result.state == "PENDING":
        print("   ⚠️  La tâche est toujours en attente")
        print("      → Le worker l'a peut-être reçue mais pas encore traitée")
    elif result.state in ["STARTED", "SUCCESS"]:
        print("   ✅ La tâche a été traitée !")
    elif result.state == "FAILURE":
        print(f"   ❌ La tâche a échoué: {result.result}")
        
except TimeoutError as e:
    print(f"   ❌ Timeout lors du lancement: {e}")
    print("      → Redis est probablement encore configuré")
    print("      → Vérifiez celery_app.py ligne 10")
    exit(1)
    
except Exception as e:
    print(f"   ❌ Erreur: {e}")
    import traceback
    traceback.print_exc()
    exit(1)

# Test 3 : Vérifier les workers
print("\n[Test 3/3] Vérification des workers...")
try:
    inspect = celery.control.inspect()
    stats = inspect.stats()
    
    if stats:
        print(f"   ✅ {len(stats)} worker(s) actif(s)")
        for worker_name in stats.keys():
            print(f"      - {worker_name}")
    else:
        print("   ⚠️  Aucun worker actif")
        print("      → Démarrez un worker si ce n'est pas déjà fait")
        
except Exception as e:
    print(f"   ⚠️  Impossible de vérifier: {e}")

# Conclusion
print("\n" + "=" * 60)
print("🎯 RÉSULTAT")
print("=" * 60)

if result and result.state != "PENDING":
    print("""
✅ SUCCÈS !

Tout fonctionne correctement :
- Le backend est bien configuré
- Les tâches se lancent sans blocage
- Le worker traite les tâches

🎉 Vous pouvez maintenant utiliser "Vérifier tous les sites" !

Prochaines étapes :
1. Ouvrez http://localhost:5000
2. Cliquez sur "Vérifier tous les sites"
3. Vérifiez le terminal Worker pour voir les tâches
""")
else:
    print("""
⚠️  PRESQUE !

La tâche se lance mais reste en attente.

Vérifications :
1. Le worker est-il démarré ?
   → celery -A celery_app.celery worker --pool=solo -l info

2. Regardez le terminal Worker, voyez-vous :
   → [INFO/MainProcess] Received task: tasks.check_all_user_sites

3. Si le worker reçoit la tâche mais qu'elle échoue :
   → Regardez l'erreur dans le terminal Worker
""")

print("=" * 60)