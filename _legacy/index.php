<?php
$page=(!empty($_GET['page']))?strtolower($_GET['page']):'home';
if(!in_array($page,array('home','cv','teaching','research'))){
	$page='home';
}
$menu_active=$page;


include('include/top.php');
include('include/'.$page.'.php');
include('include/bottom.php');